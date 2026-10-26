"""Local shell-only presentation metadata editor. NOT an HTTP endpoint."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import core,device_preferences as prefs

def main():
    p=argparse.ArgumentParser(description='Edit a MAC presentation locally (no web writes)')
    p.add_argument('action',choices=('set','reset','show'))
    p.add_argument('mac')
    p.add_argument('--nickname')
    p.add_argument('--category')
    p.add_argument('--icon')
    p.add_argument('--note',help='Private local note; never exposed by GET')
    p.add_argument('--revision',type=int,help='Expected revision for compare-and-swap')
    p.add_argument('--db',type=Path,help='Optional explicit existing SQLite file on operator volume')
    options=p.parse_args()
    dbpath=options.db if options.db else core.DB_PATH
    if not dbpath.is_file():
        p.error('Database not found. Configure an EXISTING observatory SQLite database on your microSD.')
    if options.action=='show':
        with sqlite3.connect(dbpath) as db:
            db.row_factory=sqlite3.Row
            print(json.dumps(prefs.read_presentation(db,options.mac),ensure_ascii=False))
        return
    with sqlite3.connect(dbpath,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        # Existing schema must be migrated by the application in core.init_db()
        if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_presentation_overrides'").fetchone():
            p.error('Presentation table not initialized. Start the upgraded server safely first.')
        if options.action=='set':
            revision=prefs.save(db,options.mac,nickname=options.nickname,
                               category=options.category,icon=options.icon,
                               note=options.note,expected_revision=options.revision)
            print('Saved revision',revision)
        else:
            print('Removed',prefs.delete(db,options.mac,expected_revision=options.revision),'override(s)')

if __name__=='__main__':main()
