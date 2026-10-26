"""Bounded cached read of already-retained names; no probes or writes."""
import json
from datetime import datetime,timezone,timedelta
from .query_cache import QueryCache
_cache=QueryCache(ttl=300,entries=32,byte_limit=256*1024,readers=1)

def hints(db,db_path,mac):
    def compute():
        cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        rows=db.execute("SELECT ts,payload FROM router_client_samples WHERE mac=? AND ts>=? AND json_array_length(payload,'$.names')>0 ORDER BY ts DESC,id DESC LIMIT 8",(mac,cutoff))
        return [dict(names=json.loads(payload).get('names',[]),device_types=json.loads(payload).get('device_types',[]),observed_at=ts) for ts,payload in rows]
    return _cache.get((str(db_path),mac),0,compute,lambda:0)
