"""Reproducible SYNTHETIC historian benchmark (never reads deployed databases)."""
import argparse
import concurrent.futures
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app import core,historian


def make_fixture(samples_per_day):
    now=datetime.now(timezone.utc)
    payload=json.dumps({
        'metrics':{'cpu_pct':0,'memory_pct':44,'optical_rx_dbm':-22},
        'wan_states':{'wan0':{'services':['Internet']}},
        'interfaces':{'wan0':{'rx_bytes':123456789,'tx_bytes':0}},
        'clients':[{'reported_status':'Online'}],
        'stations':[{'rssi_dbm':-59}],
    })
    with core.connect() as db:
        for day in range(30):
            for step in range(samples_per_day):
                offset=day*86400+step*86400/samples_per_day
                ts=(now-timedelta(seconds=offset)).isoformat()
                db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',(ts,payload))
                db.execute('INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)',
                           (ts,1,0,1,None))
    return samples_per_day*30


def invoke(period,view):
    started=time.perf_counter()
    value=historian.overview_history(period,view)
    return round((time.perf_counter()-started)*1000,3),len(json.dumps(value,ensure_ascii=False).encode())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples-per-day',type=int,default=120)
    options=parser.parse_args()
    if not 1<=options.samples_per_day<=1440:parser.error('1..1440 synthetic samples per day')
    with tempfile.TemporaryDirectory(prefix='synthetic-network-history-') as directory:
        with patch.object(core,'DB_PATH',Path(directory)/'fixture.db'):
            core.init_db()
            rows=make_fixture(options.samples_per_day)
            results=[]
            for period in ('24h','7d','1m'):
                for view in ('summary','full'):
                    with historian._overview_mutex:historian._overview_cache.clear()
                    cold,body=invoke(period,view)
                    warm_times=[invoke(period,view)[0] for _ in range(4)]
                    with historian._overview_mutex:historian._overview_cache.clear()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        concurrent_times=list(pool.map(lambda _:invoke(period,view)[0],range(4)))
                    results.append({
                        'period':period,'view':view,'cold_ms':cold,'warm_ms_median':round(statistics.median(warm_times),3),
                        'four_client_wall_relative_ms_max':max(concurrent_times),'four_client_times_ms':concurrent_times,
                        'serialized_bytes':body,
                    })
            summary={x['period']:x for x in results if x['view']=='summary'}
            for item in results:
                if item['view']=='full':
                    other=summary[item['period']]
                    item['summary_payload_reduction_pct']=round(100*(1-other['serialized_bytes']/max(item['serialized_bytes'],1)),2)
            print(json.dumps({
                'warning':'SYNTHETIC BENCHMARK ONLY. Not an S7 LAN measurement or production SLA.',
                'environment':{'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),
                               'sqlite_file':'temporary test-only disk','rows_huawei':rows,
                               'rows_probes':rows,'samples_per_day':options.samples_per_day,
                               'clients':(1,4),'trials':4},
                'results':results
            },ensure_ascii=False,indent=2))


if __name__=='__main__':main()
