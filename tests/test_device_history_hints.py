import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from app import core
from app.device_history_hints import hints

class HistoryHintTests(unittest.TestCase):
    def test_retained_names_enrich_blank_live_observation_without_rewriting_archive(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(core,'DB_PATH',Path(folder)/'fixture.db'):
            core.init_db();now=datetime.now(timezone.utc);mac='00:11:22:33:44:55'
            previous={'mac':mac,'names':['MiTV'],'device_types':['android-dhcp-11'],'ports':['wifi:wlan0'],'reported_status':'Online'}
            current={**previous,'names':[],'device_types':['--']}
            with core.connect() as db:
                for date,payload in [(now-timedelta(hours=6),previous),(now,current)]:
                    db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',(1,date.isoformat(),mac,json.dumps(payload)))
            client=core.get_router_clients()['clients'][0]
            self.assertEqual(client['classification']['category'],'smart_tv');self.assertEqual(client['classification']['display_name_source'],'history')
            self.assertEqual(client['names'],[])
            with core.connect() as db:
                self.assertEqual(json.loads(db.execute('SELECT payload FROM router_client_samples ORDER BY id DESC LIMIT 1').fetchone()[0]),current)
