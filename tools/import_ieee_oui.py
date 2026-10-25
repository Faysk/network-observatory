"""Convert operator-downloaded IEEE MA-L/MA-M/MA-S CSV files to a local registry.

No network access. Output should stay private on the configured device unless
the licensing and distribution terms are reviewed.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.device_identity import load_ieee_csv

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ma-l',type=Path)
    parser.add_argument('--ma-m',type=Path)
    parser.add_argument('--ma-s',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    provided=[(b,p) for b,p in ((24,args.ma_l),(28,args.ma_m),(36,args.ma_s)) if p]
    if not provided:parser.error('Supply at least one locally downloaded IEEE CSV')
    assignments={}
    for bits,path in provided:
        for item in load_ieee_csv(path,bits):
            assignments[(bits,item['prefix'])]=item
    result={'version':'ieee-operator-import-'+datetime.now(timezone.utc).strftime('%Y%m%d'),
            'source':'IEEE Registration Authority CSV; operator-provided offline',
            'license_note':'Review the IEEE redistribution/licensing terms before publishing.',
            'assignments':list(assignments.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Imported',len(assignments),'prefixes. Registry saved locally to',args.output)

if __name__=='__main__':main()
