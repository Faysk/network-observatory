"""Authenticated local-shell administration; no HTTP mutation endpoint."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import core, device_groups


def main():
    p = argparse.ArgumentParser(description='Associate identities explicitly without merging history')
    p.add_argument('action', choices=('associate', 'dissociate', 'list'))
    p.add_argument('macs', nargs='*')
    p.add_argument('--db', type=Path, default=core.DB_PATH)
    args = p.parse_args()
    if not args.db.is_file():
        p.error('An existing configured microSD database is required')
    with sqlite3.connect(args.db, timeout=10) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if args.action != 'list' else 'BEGIN')
        if args.action == 'associate':
            print(device_groups.associate(db, args.macs))
        elif args.action == 'dissociate':
            if len(args.macs) != 1:
                p.error('Specify exactly one identity')
            print('Removed', device_groups.dissociate(db, args.macs[0]))
        else:
            print(json.dumps([dict(x) for x in db.execute('SELECT * FROM device_group_members')]))


if __name__ == '__main__':
    main()
