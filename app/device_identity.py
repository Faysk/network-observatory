"""Offline, read-only metadata about MAC address assignments (not device identity).

IEEE MA-L/MA-M/MA-S are assignments to an interface-address registrant. They do
NOT establish a device model, OS, owner, or physical device manufacturer.
No network calls, private inventory indexes, or persistence are performed here.
"""
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

DATASET = Path(__file__).resolve().parent / 'data' / 'oui.json'
EUI48 = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$', re.I)

def normalize_mac(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower().replace('-', ':')
    if re.fullmatch(r'[0-9a-f]{12}', value):
        value = ':'.join(value[i:i+2] for i in range(0, 12, 2))
    return value if EUI48.fullmatch(value) else None

def mac_type(value):
    normalized = normalize_mac(value)
    if normalized is None or normalized in ('00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff'):
        return 'invalid'
    first = int(normalized[:2], 16)
    if first & 0x01:
        return 'multicast'
    if first & 0x02:
        return 'locally_administered'
    return 'global'

@lru_cache(maxsize=1)
def _dataset():
    # Explicitly packaged tiny bootstrap dataset; optional local IEEE dataset can
    # be updated offline by the operator. Never auto-fetch or infer vendor when absent.
    try:
        raw=json.loads(DATASET.read_text(encoding='utf-8'))
        entries={}
        for item in raw.get('assignments', []):
            bits=item.get('prefix_bits')
            prefix=item.get('prefix')
            vendor=item.get('registrant')
            if bits not in (24, 28, 36) or not isinstance(prefix,str) or not re.fullmatch(r'[0-9A-Fa-f]+',prefix):
                continue
            if len(prefix)!=bits//4 or not isinstance(vendor,str) or not 1<=len(vendor)<=160:
                continue
            entries[(bits,prefix.upper())]=vendor
        return raw.get('version'), MappingProxyType(entries)
    except (OSError, ValueError, TypeError):
        return None, MappingProxyType({})

def enrich_mac(value, *, dataset=None):
    kind=mac_type(value)
    base={'mac_type':kind,'oui_vendor':None,'oui_prefix_bits':None,
          'oui_dataset_version':None,'sources':[]}
    if kind != 'global':
        return base
    norm=normalize_mac(value)
    version,assignments=dataset if dataset is not None else _dataset()
    base['oui_dataset_version']=version
    compact=norm.replace(':','').upper()
    for bits in (36,28,24):
        vendor=assignments.get((bits,compact[:bits//4]))
        if vendor:
            base.update(oui_vendor=vendor,oui_prefix_bits=bits,
                        sources=[{'field':'oui_vendor','source':'offline_ieee_assignment',
                                  'prefix_bits':bits}])
            break
    return base

def load_ieee_csv(path, bits):
    """Build helper for an operator-provided IEEE CSV (never during API requests)."""
    if bits not in (24,28,36):raise ValueError('Invalid prefix length')
    entries=[]
    with Path(path).open(encoding='utf-8-sig',newline='') as file:
        for row in csv.DictReader(file):
            prefix=(row.get('Assignment') or '').strip().upper().replace(':','').replace('-','')
            vendor=(row.get('Organization Name') or '').strip()
            if re.fullmatch('[0-9A-F]{'+str(bits//4)+'}',prefix) and 1<=len(vendor)<=160:
                entries.append({'prefix':prefix,'prefix_bits':bits,'registrant':vendor})
    return entries
