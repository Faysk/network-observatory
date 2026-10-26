"""Explicit, resumable offline chart rebuild. Only existing selected DBs are opened.

Run from an authenticated operator shell; default and output stay on the archive
volume. No collector, target probe, retention changes or internal fallback.
"""
import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import read_models


def rebuild(path, kind, batch=32, refresh_wifi=False):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Existing archive required; no database or directory will be created')
    total = 0
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=rw', uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA busy_timeout=10000')
        fn = (read_models.backfill_host if kind == 'host' else
              read_models.refresh_wifi_context if refresh_wifi else read_models.backfill_router)
        cursors = {}
        while True:
            committed = 0
            began = time.monotonic()
            with db:
                # Batch memory stays small; amortize SD fsync without holding a
                # write lock for the entire archive. A slow individual batch
                # may exceed this soft time budget, but never its row bound.
                while committed < 2048 and time.monotonic()-began < 2:
                    count = fn(db, batch, cursors=cursors)
                    committed += count
                    if not count:
                        break
            total += committed
            if not count:
                break
            # Yield between bounded transactions to allow the active collector.
            time.sleep(.02)
    return total


def main():
    p = argparse.ArgumentParser(description='Build lossless, compact chart read models on the configured archive volume')
    p.add_argument('--router-db', type=Path)
    p.add_argument('--host-db', type=Path)
    p.add_argument('--batch', type=int, default=32)
    p.add_argument('--refresh-wifi', action='store_true', help='Recalcular somente projeções antigas de banda/interface Wi-Fi a partir das leituras brutas')
    args = p.parse_args()
    if not args.router_db and not args.host_db:
        p.error('Select at least one existing database')
    if args.refresh_wifi and (not args.router_db or args.host_db):
        p.error('--refresh-wifi exige apenas --router-db com arquivo já existente')
    if not 1 <= args.batch <= 128:
        p.error('Batch must be between 1 and 128')
    for kind, path in [('router', args.router_db), ('host', args.host_db)]:
        if path:
            started = time.perf_counter()
            count = rebuild(path, kind, args.batch, args.refresh_wifi)
            print(json.dumps({'kind': kind, 'projected_rows': count, 'elapsed_seconds': round(time.perf_counter()-started, 3)}), flush=True)


if __name__ == '__main__':
    main()
