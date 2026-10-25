"""Operator-only device presentation metadata. NEVER mutate Huawei observations.

No HTTP write endpoint. All mutations require local shell/CLI access to DB volume.
"""
from datetime import datetime,timezone
from .device_identity import normalize_mac
from .device_classifier import CATEGORIES

ICONS=CATEGORIES
SELECT_FIELDS='nickname,category,icon,revision'

def check_mac(mac):
    normalized=normalize_mac(mac)
    if not normalized or normalized in ('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff'):
        raise ValueError('Invalid EUI-48')
    return normalized

def text_value(value,maxlength):
    if value is None:return None
    if not isinstance(value,str):raise ValueError('Expected text')
    value=value.strip()
    if not value:return None
    if len(value)>maxlength or any(not c.isprintable() for c in value):
        raise ValueError('Invalid or too long text')
    return value

def validate(nickname=None,category=None,icon=None,note=None):
    nickname=text_value(nickname,64)
    note=text_value(note,250)
    if category not in (None,*CATEGORIES-{ 'unknown' }):
        raise ValueError('Unknown category')
    if icon not in (None,*ICONS-{ 'unknown' }):
        raise ValueError('Unknown icon')
    return nickname,category,icon,note

def read_presentation(db,mac):
    try:
        normalized=check_mac(mac)
    except ValueError:
        return {'source':'none','nickname':None,'category':None,'icon':None,'revision':None}
    row=db.execute('SELECT '+SELECT_FIELDS+' FROM device_presentation_overrides WHERE mac=?',(normalized,)).fetchone()
    if row is None:
        return {'source':'none','nickname':None,'category':None,'icon':None,'revision':None}
    return {'source':'manual','nickname':row['nickname'],'category':row['category'],
            'icon':row['icon'],'revision':row['revision']}

def save(db,mac,*,nickname=None,category=None,icon=None,note=None,expected_revision=None):
    mac=check_mac(mac)
    nickname,category,icon,note=validate(nickname,category,icon,note)
    if not any(x is not None for x in (nickname,category,icon,note)):
        raise ValueError('At least one field is required, use delete to reset')
    current=db.execute('SELECT revision FROM device_presentation_overrides WHERE mac=?',(mac,)).fetchone()
    actual=current['revision'] if current else None
    if expected_revision is not None and expected_revision!=actual:
        raise ValueError('Version conflict')
    version=(actual or 0)+1
    db.execute('INSERT INTO device_presentation_overrides(mac,nickname,category,icon,note,revision,updated_at) '
               'VALUES(?,?,?,?,?,?,?) ON CONFLICT(mac) DO UPDATE SET '
               'nickname=excluded.nickname,category=excluded.category,icon=excluded.icon,'
               'note=excluded.note,revision=excluded.revision,updated_at=excluded.updated_at',
               (mac,nickname,category,icon,note,version,datetime.now(timezone.utc).isoformat()))
    return version

def delete(db,mac,expected_revision=None):
    mac=check_mac(mac)
    current=db.execute('SELECT revision FROM device_presentation_overrides WHERE mac=?',(mac,)).fetchone()
    actual=current['revision'] if current else None
    if expected_revision is not None and actual!=expected_revision:raise ValueError('Version conflict')
    return db.execute('DELETE FROM device_presentation_overrides WHERE mac=?',(mac,)).rowcount
