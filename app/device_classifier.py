"""Deterministic, explainable *suggestions* for a network interface, not device identity.

Only already observed Huawei fields are used; vendor OUI is NOT a model/class proof.
"""
import re
import unicodedata
from .device_identity import enrich_mac

VERSION='2026-10-v1'
CATEGORIES=frozenset(('smartphone','tablet','laptop','desktop','game_console','smart_tv',
                     'streaming_box','printer','camera','robot_vacuum','network_device','iot','unknown'))
PLATFORMS=frozenset(('android','ios','windows','linux','macos','unknown'))

def _clean(value):
    text=unicodedata.normalize('NFKC',str(value or '')).casefold()
    return re.sub(r'[^a-z0-9]+','-',text).strip('-')[:128]

def classify_client(client):
    """Pure, bounded classifier. Returned words are hypotheses, never confirmations."""
    names=[_clean(x) for x in (client.get('names') or []) if isinstance(x,str)][:16]
    types=[_clean(x) for x in (client.get('device_types') or []) if isinstance(x,str)][:16]
    identity=client.get('identity') if isinstance(client.get('identity'),dict) else enrich_mac(client.get('mac'))
    candidates=[]
    evidence=[]
    platform='unknown'
    def add(category,rule,source,strength):
        candidates.append((category,strength))
        evidence.append({'field':source,'rule':rule,'source':'huawei_observed','confidence':strength})
    for name in names+types:
        if re.search(r'(^|-)roomba(-|$)',name) or re.search(r'(^|-)irobot(-|$)',name):
            add('robot_vacuum','named_robot_vacuum','names/device_types','high')
        elif re.search(r'(^|-)playstation(-|$)|(^|-)ps5(-|$)|(^|-)ps4(-|$)|(^|-)xbox(-|$)',name):
            add('game_console','named_console','names/device_types','high')
        elif re.search(r'(^|-)galaxy-tab(-|$)|(^|-)ipad(-|$)|(^|-)tablet(-|$)',name):
            add('tablet','named_tablet','names/device_types','high')
        elif re.search(r'(^|-)galaxy-s\d{2}(-|$)|(^|-)s2[0-9](-|$)|(^|-)iphone(-|$)|(^|-)pixel-\d+(-|$)|(^|-)redmi-[a-z0-9]+(-|$)',name):
            add('smartphone','named_phone_family','names/device_types','medium')
        elif re.search(r'(^|-)roborock(-|$)|(^|-)deebot(-|$)',name):
            add('robot_vacuum','named_robot_vacuum','names/device_types','medium')
        elif re.search(r'(^|-)chromecast(-|$)|(^|-)fire-tv(-|$)|(^|-)apple-tv(-|$)',name):
            add('streaming_box','named_streaming_device','names/device_types','medium')
        elif re.search(r'(^|-)smart-tv(-|$)|(^|-)bravia(-|$)|(^|-)roku-tv(-|$)',name):
            add('smart_tv','named_smart_tv','names/device_types','medium')
        elif re.search(r'(^|-)printer(-|$)|(^|-)laserjet(-|$)|(^|-)deskjet(-|$)',name):
            add('printer','named_printer','names/device_types','medium')
        elif re.search(r'(^|-)ip-camera(-|$)|(^|-)webcam(-|$)',name):
            add('camera','named_camera','names/device_types','medium')
        elif re.search(r'(^|-)predator(-|$)|(^|-)notebook(-|$)|(^|-)laptop(-|$)',name):
            add('laptop','named_laptop','names/device_types','medium')
        elif re.search(r'(^|-)desktop(-|$)|(^|-)workstation(-|$)|(^|-)pc(-|$)',name):
            add('desktop','named_desktop','names/device_types','low')
        elif re.search(r'(^|-)router(-|$)|(^|-)repeater(-|$)|(^|-)access-point(-|$)',name):
            add('network_device','named_network_equipment','names/device_types','medium')
        if re.search(r'(^|-)android-dhcp(-|$)',name):
            platform='android'
            evidence.append({'field':'device_types','rule':'android_dhcp_signature',
                             'source':'huawei_observed','confidence':'medium'})
        if re.search(r'(^|-)iphone(-|$)|(^|-)ipad(-|$)',name):
            platform='ios'
            evidence.append({'field':'names/device_types','rule':'apple_mobile_hostname',
                             'source':'huawei_observed','confidence':'medium'})
    # MSFT DHCP signatures are evidence of a protocol stack, NOT proof of Windows.
    if any('msft-5-0' in x for x in types):
        evidence.append({'field':'device_types','rule':'microsoft_dhcp_signature_only',
                         'source':'huawei_observed','confidence':'low'})
    unique=set(c for c,_ in candidates)
    conflicts=sorted(unique) if len(unique)>1 else []
    if len(unique)!=1:
        category='unknown'
        confidence='unknown'
    else:
        category=next(iter(unique))
        ranks={'low':1,'medium':2,'high':3}
        confidence=max((strength for _,strength in candidates),key=lambda x:ranks[x])
    # A random/private/global MAC or vendor alone never determines a category.
    return {'category':category,'platform_family':platform,
            'display_name_suggestion':next((x for x in (client.get('names') or []) if isinstance(x,str) and x.strip()),None),
            'confidence':confidence,'evidence':evidence[:32],
            'conflicts':conflicts,'classification_version':VERSION,
            'confirmed':False}
