"""Manually push REAL validated readings from a future authorized collector.

Usage: FNO_INGEST_TOKEN=... python tools/ingest_example.py readings.json
JSON: {"source":"approved-huawei-adapter", "metrics":{"cpu_pct":31}}
Never put router credentials in this tool's arguments or fixtures.
"""
import json
import os
import sys
import urllib.request

if __name__ == '__main__':
    if len(sys.argv) != 2 or not os.environ.get('FNO_INGEST_TOKEN'):
        raise SystemExit('Usage: set FNO_INGEST_TOKEN, python tools/ingest_example.py readings.json')
    with open(sys.argv[1], encoding='utf-8') as f: data = json.load(f)
    body = json.dumps(data).encode()
    req = urllib.request.Request('http://127.0.0.1:8765/api/ingest/router', data=body, method='POST', headers={
        'X-API-Key': os.environ['FNO_INGEST_TOKEN'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as r:
        print(r.read().decode())
