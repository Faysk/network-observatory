"""Reversible operator associations. Never merge or rewrite raw observations."""
import unicodedata
import uuid
from datetime import datetime, timezone
from .device_preferences import check_mac


def associate(db, macs):
    macs = sorted({check_mac(mac) for mac in macs})
    if not 2 <= len(macs) <= 32:
        raise ValueError('Choose 2 to 32 distinct identities')
    for mac in macs:
        if not db.execute('SELECT 1 FROM router_client_samples WHERE mac=? LIMIT 1', (mac,)).fetchone():
            raise ValueError('Identity has not been observed')
        if db.execute('SELECT 1 FROM device_group_members WHERE mac=?', (mac,)).fetchone():
            raise ValueError('Identity already associated; remove its association first')
    group = uuid.uuid4().hex
    stamp = datetime.now(timezone.utc).isoformat()
    db.executemany('INSERT INTO device_group_members(mac,group_id,source,updated_at) VALUES(?,?,?,?)',
                   [(mac, group, 'manual', stamp) for mac in macs])
    return group


def dissociate(db, mac):
    mac = check_mac(mac)
    row = db.execute('SELECT group_id FROM device_group_members WHERE mac=?', (mac,)).fetchone()
    if not row:
        return 0
    count = db.execute('DELETE FROM device_group_members WHERE mac=?', (mac,)).rowcount
    # A group must represent at least two identities.
    if db.execute('SELECT COUNT(*) FROM device_group_members WHERE group_id=?', (row[0],)).fetchone()[0] < 2:
        db.execute('DELETE FROM device_group_members WHERE group_id=?', (row[0],))
    return count


def enrich(db, clients):
    members = {row['mac']: row['group_id'] for row in db.execute('SELECT mac,group_id FROM device_group_members')}
    buckets = {}
    for item in clients:
        # No IP/RSSI/vendor-only inference; equal names are at most weak suggestions.
        names = item.get('names') or []
        name = unicodedata.normalize('NFKC', str(names[0])[:256]).casefold().strip() if names else ''
        if len(name) >= 4 and name not in {'unknown', 'android', 'iphone', 'desktop', 'localhost'}:
            buckets.setdefault(name, []).append(item)
    for item in clients:
        group = members.get(item.get('mac'))
        item['association'] = {'group_id': group, 'source': 'manual' if group else None}
        names = item.get('names') or []
        name = unicodedata.normalize('NFKC', str(names[0])[:256]).casefold().strip() if names else ''
        possible = []
        for other in buckets.get(name, [])[:32]:
            if other.get('mac') == item.get('mac'):
                continue
            a, b = item.get('classification') or {}, other.get('classification') or {}
            conflicts = any(a.get(k) not in (None, 'unknown') and b.get(k) not in (None, 'unknown')
                            and a[k] != b[k] for k in ('category', 'platform_family'))
            possible.append({'mac': other['mac'], 'confidence': 'low', 'conflict': conflicts,
                             'reasons': ['same_reported_name'], 'confirmed': False})
            if len(possible) == 3:
                break
        item['possible_relations'] = possible
