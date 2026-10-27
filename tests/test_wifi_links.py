"""Synthetic Wi-Fi association and band history tests; never contact a router."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import core, historian, read_models
from app.wifi_links import station_links, band_rssi


class WifiEvidenceTests(unittest.TestCase):
    def test_bands_require_same_snapshot_interface_mapping(self):
        wifi={"wlan1":{"band":"2.4GHz","channel":6},"wlan5":{"band":"5GHz","channel":100}}
        stations=[{"interface":"wlan1","rssi_dbm":-70},
                  {"interface":"wlan5","rssi_dbm":-55},
                  {"interface":"wlan5","rssi_dbm":-65},
                  {"interface":"wlan9","rssi_dbm":-10}]
        self.assertEqual(station_links(stations,wifi),[
            {"interface":"wlan1","band":"2.4GHz","channel":6},
            {"interface":"wlan5","band":"5GHz","channel":100},
            {"interface":"wlan9","band":None,"channel":None}])
        self.assertEqual(band_rssi({"wifi":wifi,"stations":stations}),
                         {"rssi_24_dbm":-70.0,"rssi_5_dbm":-60.0})
        self.assertEqual(band_rssi({"stations":stations}),
                         {"rssi_24_dbm":None,"rssi_5_dbm":None})
        self.assertEqual(station_links([{"interface":"wlan5"}],{}),
                         [{"interface":"wlan5","band":None,"channel":None}])
        self.assertEqual(station_links([{"interface":"wlan5"}],{"wlan5":{"band":"6GHz","channel":5}})[0]["band"],None)

    def test_signal_means_exclude_malformed_and_unavailable_values(self):
        from app.historian import sample
        payload={'stations':[
            {'interface':'wlan1','rssi_dbm':-65,'snr_db_reported':0,
             'rx_link_mbps':0,'tx_link_mbps':300},
            {'interface':'wlan5','rssi_dbm':-55},
            {'interface':'wlan2','rssi_dbm':'unknown'},
            {'interface':'wlan3','rssi_dbm':True},
            {'interface':'wlan4','rssi_dbm':900},
            {'interface':'wlan6','rssi_dbm':float('inf')}]}
        self.assertEqual(read_models.overview_point(payload)['rssi_dbm'],-60)
        self.assertIsNone(read_models.overview_point(
            {'stations':[{'rssi_dbm':'-60'},{'rssi_dbm':False}]} )['rssi_dbm'])
        single=sample('2026-10-27T12:00:00+00:00',
                      {'reported_status':'Online','stations':[{'rssi_dbm':True,
                         'snr_db_reported':'unknown','rx_link_mbps':float('inf'),
                         'tx_link_mbps':-1}]})
        self.assertIsNone(single['rssi_dbm'])
        self.assertIsNone(single['snr_db'])
        self.assertIsNone(single['link_rx_phy_mbps'])
        self.assertIsNone(single['link_tx_phy_mbps'])
        legitimate=sample('2026-10-27T12:00:00+00:00',payload)
        self.assertEqual(legitimate['rssi_dbm'],-65)
        self.assertEqual(legitimate['snr_db'],0)
        self.assertEqual(legitimate['link_rx_phy_mbps'],0)
        self.assertEqual(legitimate['link_tx_phy_mbps'],300)

    def test_legacy_rssi_projection_recomputes_from_raw_without_mutating_archive(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core,'DB_PATH',Path(temp)/'router.db'):
            core.init_db()
            ts=(datetime.now(timezone.utc)-timedelta(seconds=90)).isoformat()
            payload={'metrics':{},'stations':[
                {'interface':'wlan1','rssi_dbm':-70},
                {'interface':'wlan5','rssi_dbm':True}],
                'wifi':{'wlan1':{'band':'2.4GHz'},
                        'wlan5':{'band':'5GHz'}}}
            with core.connect() as db:
                rid=db.execute('INSERT INTO huawei_samples(ts,payload) VALUES (?,?)',
                               (ts,json.dumps(payload))).lastrowid
                # Old cached mean was corrupted, despite having band metadata.
                old={'rssi_dbm':-34.5,'rssi_24_dbm':-70,
                     'rssi_5_dbm':None}
                db.execute('INSERT INTO router_chart_points(ts,id,payload) VALUES (?,?,?)',
                           (ts,rid,json.dumps(old)))
                original=db.execute('SELECT payload FROM huawei_samples WHERE id=?',(rid,)).fetchone()[0]
                points=list(read_models.overview_rows(db,ts,ts))
                self.assertEqual(len(points),1)
                self.assertEqual(points[0][1]['rssi_dbm'],-70)
                self.assertIsNone(points[0][1]['rssi_5_dbm'])
                self.assertEqual(read_models.refresh_wifi_context(db,batch=10),1)
                refreshed=json.loads(db.execute(
                    'SELECT payload FROM router_chart_points WHERE id=?',(rid,)).fetchone()[0])
                self.assertEqual(refreshed['rssi_dbm'],-70)
                self.assertEqual(refreshed['_signal_calc_version'],1)
                self.assertEqual(read_models.refresh_wifi_context(db,batch=10),0)
                self.assertEqual(db.execute('SELECT payload FROM huawei_samples WHERE id=?',(rid,)).fetchone()[0],original)
                self.assertEqual(list(read_models.overview_rows(db,ts,ts))[0][1]['rssi_dbm'],-70)

    def test_raw_fallback_and_compact_projections_match_after_refresh(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core,"DB_PATH",Path(temp)/"router.db"):
            core.init_db()
            ts=(datetime.now(timezone.utc)-timedelta(seconds=75)).isoformat()
            mac="02:00:00:00:00:01"
            station={"mac":mac,"interface":"wlan5","rssi_dbm":-60}
            router={"metrics":{},"interfaces":{},"stations":[station],
                    "wifi":{"wlan5":{"band":"5GHz","channel":44}}}
            client={"mac":mac,"reported_status":"Online","names":["Fixture"],
                    "ips":["192.0.2.19"],"ports":["wlan5"],"stations":[station]}
            with core.connect() as db:
                sid=db.execute("INSERT INTO huawei_samples(ts,payload) VALUES(?,?)",
                               (ts,json.dumps(router))).lastrowid
                did=db.execute("INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)",
                               (sid,ts,mac,json.dumps(client))).lastrowid
                read_models.init_router(db)
                # A compact projection generated by a prior release.
                db.execute("INSERT INTO router_chart_points(ts,id,payload) VALUES(?,?,?)",
                           (ts,sid,json.dumps({"rssi_dbm":-60})))
                db.execute("INSERT INTO client_chart_points(mac,ts,id,payload) VALUES(?,?,?,?)",
                           (mac,ts,did,json.dumps({"stations":[station],"reported_status":"Online"})))
                saved=db.execute("SELECT payload FROM huawei_samples").fetchone()[0]
                original=db.execute("SELECT payload FROM router_client_samples").fetchone()[0]
                self.assertEqual(read_models.refresh_wifi_context(db,batch=4),2)
                self.assertEqual(read_models.refresh_wifi_context(db,batch=4),0)
                self.assertEqual(db.execute("SELECT payload FROM huawei_samples").fetchone()[0],saved)
                self.assertEqual(db.execute("SELECT payload FROM router_client_samples").fetchone()[0],original)
                overview=list(read_models.overview_rows(db,(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),
                                                             datetime.now(timezone.utc).isoformat()))
                self.assertEqual(overview[0][1]["rssi_5_dbm"],-60)
                self.assertIsNone(overview[0][1]["rssi_24_dbm"])
                compact=list(read_models.device_rows(db,mac,(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),
                                                               datetime.now(timezone.utc).isoformat()))
                self.assertEqual(json.loads(compact[0]["payload"])["wifi_links"],
                                 [{"interface":"wlan5","band":"5GHz","channel":44}])
            bundle=historian.device_history(mac.replace(":",""),"1h")
            self.assertEqual(bundle["wifi_history"][0]["links"][0]["band"],"5GHz")
            self.assertEqual(bundle["wifi_history"][0]["links"][0]["interface"],"wlan5")
            self.assertEqual(bundle["latest"]["wifi_links"][0]["channel"],44)


if __name__=="__main__":
    unittest.main()
