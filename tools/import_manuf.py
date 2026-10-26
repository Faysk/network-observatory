"""Compile an operator-downloaded Wireshark manuf file; no network/device access."""
import argparse,hashlib,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.import_ieee_oui import save_atomic
from app.device_identity import MAX_ENTRIES,MAX_REGISTRY_BYTES

def convert(path):
    if Path(path).stat().st_size>MAX_REGISTRY_BYTES:raise ValueError('Source too large')
    entries={}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        parts=line.split(None,2)
        if len(parts)<2:continue
        prefix,_,mask=parts[0].partition('/');bits=int(mask) if mask else 24
        if bits not in (24,28,36):continue
        raw=prefix.replace(':','').upper()
        if not re.fullmatch('[0-9A-F]{6,12}',raw) or len(raw)<bits//4:raise ValueError('Invalid prefix')
        if int(raw[:2],16)&3:continue
        vendor=' '.join((parts[2] if len(parts)>2 else parts[1]).split())
        if not vendor or len(vendor)>160 or any(ord(c)<32 for c in vendor):continue
        key=(bits,raw[:bits//4])
        if key in entries and entries[key]!=vendor:raise ValueError('Conflicting assignment')
        entries[key]=vendor
    if not entries or len(entries)>MAX_ENTRIES:raise ValueError('Invalid source size')
    body=''.join(str(bits)+'\t'+prefix+'\t'+vendor+'\n' for (bits,prefix),vendor in sorted(entries.items()))
    digest=hashlib.sha256(body.encode()).hexdigest()[:16]
    result='# version=wireshark-manuf-'+digest+'\n# provider=wireshark_manuf\n# source_url=https://www.wireshark.org/download/automated/data/manuf\n'+body
    if len(result.encode())>MAX_REGISTRY_BYTES:raise ValueError('Runtime snapshot too large')
    return result,len(entries)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--replace',action='store_true');a=p.parse_args()
    text,count=convert(a.input);save_atomic(a.output,text,replace=a.replace);print('Compiled',count,'public assignments; source Wireshark, not a fresh IEEE download')
if __name__=='__main__':main()
