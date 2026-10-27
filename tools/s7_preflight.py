"""Conservative local preflight for S7/Termux. No router login or DB mutation.

Only localhost GET /api/status, filesystem free-space checks and SQLite
read-only schema probes. Output deliberately excludes paths, IPs, MACs and
sample payloads. It is NOT an integrity-check or hardware certification.
"""
import argparse
from contextlib import closing
import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MIB=1024*1024


def check(name,status,detail):
    return {'name':name,'status':status,'detail':detail}


def sqlite_readonly(path):
    """Probe schema without changing data or running expensive integrity scans."""
    if not path.is_file():
        return check('sqlite','fail','Database file is missing')
    try:
        uri=path.resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=2)) as db:
            db.execute('PRAGMA query_only=ON')
            table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        if table is None:
            return check('sqlite','fail','No SQLite tables found')
        return check('sqlite','ok','Read-only schema probe succeeded')
    except (OSError,sqlite3.Error,ValueError):
        return check('sqlite','fail','Read-only SQLite probe unavailable')


def local_status(origin):
    parsed=urllib.parse.urlsplit(origin)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1','localhost')
            or parsed.username or parsed.password or parsed.path not in ('','/')
            or parsed.query or parsed.fragment or parsed.port is None):
        raise ValueError('Only explicit HTTP loopback origins with a port are supported')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,msg,headers,newurl):
            return None

    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    req=urllib.request.Request(origin.rstrip('/')+'/api/status',
                               headers={'Accept':'application/json','Accept-Encoding':'identity'})
    with opener.open(req,timeout=4) as response:
        if response.status!=200:
            raise ValueError('Non-200 API result')
        raw=response.read(2*MIB+1)
        if len(raw)>2*MIB:
            raise ValueError('API response exceeds 2 MiB')
    result=json.loads(raw)
    if not isinstance(result,dict) or 'router' not in result or 'collector' not in result:
        raise ValueError('Unsupported API status payload')
    return result


def run_preflight(router_db,host_db=None,internal_dir=None,origin='http://127.0.0.1:8765',
                  min_free_mib=2048,skip_api=False):
    results=[]
    home=Path(internal_dir) if internal_dir is not None else Path.home()
    try:
        available=shutil.disk_usage(home).free
        results.append(check('internal_free_space','ok' if available>=min_free_mib*MIB else 'fail',
                             'Internal reserve meets threshold' if available>=min_free_mib*MIB
                             else 'Internal reserve below configured threshold'))
    except OSError:
        results.append(check('internal_free_space','fail','Internal storage inaccessible'))

    db_path=Path(router_db) if router_db else None
    if db_path is None:
        results.append(check('router_sqlite','fail','Pass --router-db or set FNO_DB'))
    else:
        report=sqlite_readonly(db_path)
        results.append(check('router_sqlite',report['status'],report['detail']))
        try:
            # Indicates a possible same-volume risk; st_dev is not a proof
            # of physical microSD ownership on all Android storage layers.
            same_volume=db_path.stat().st_dev==home.stat().st_dev
            results.append(check('database_volume','warn' if same_volume else 'ok',
                                 'Database may share the internal volume' if same_volume
                                 else 'Database is on a distinct mounted device'))
        except OSError:
            results.append(check('database_volume','warn','Cannot verify storage separation'))

    if host_db:
        report=sqlite_readonly(Path(host_db))
        results.append(check('host_sqlite',report['status'],report['detail']))
    else:
        results.append(check('host_sqlite','warn','Host database was not supplied'))

    if skip_api:
        results.append(check('local_api','warn','API check explicitly skipped'))
    else:
        try:
            state=local_status(origin)
            results.append(check('local_api','ok','Loopback status endpoint responds with expected schema'))
            collector=(state.get('collector') or {}).get('state')
            if collector=='auth_blocked':
                results.append(check('collector','fail','Collector authentication is blocked'))
            elif collector in ('ok','collecting'):
                results.append(check('collector','ok','Collector reports an active state'))
            else:
                results.append(check('collector','warn','Collector requires operational verification'))
        except (ValueError,TypeError,urllib.error.URLError,OSError,json.JSONDecodeError):
            results.append(check('local_api','fail','Loopback status endpoint unavailable or invalid'))

    outcome='fail' if any(r['status']=='fail' for r in results) else (
        'incomplete' if any(r['status']=='warn' for r in results) else 'pass')
    return {'schema_version':1,'result':outcome,'checks':results,
            'limitations':'Lightweight, read-only synthetic-safe preflight; no microSD endurance, API load, screen or router validation'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--router-db',default=os.environ.get('FNO_DB',''),
                        help='Existing router SQLite path; never printed')
    parser.add_argument('--host-db',default='',help='Optional existing host SQLite path; never printed')
    parser.add_argument('--internal-dir',default=str(Path.home()))
    parser.add_argument('--min-internal-free-mib',type=int,default=2048)
    parser.add_argument('--origin',default='http://127.0.0.1:8765')
    parser.add_argument('--skip-api',action='store_true')
    args=parser.parse_args(argv)
    if not 0<=args.min_internal_free_mib<=1024*1024:
        parser.error('Invalid reserve threshold')
    try:
        report=run_preflight(args.router_db,args.host_db,args.internal_dir,args.origin,
                             args.min_internal_free_mib,args.skip_api)
    except ValueError:
        parser.error('Invalid preflight configuration')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return {'pass':0,'incomplete':2,'fail':1}[report['result']]


if __name__=='__main__':
    sys.exit(main())
