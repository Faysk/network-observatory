"""Durable, private local outbox. Payloads only; never credentials or session data."""
import json
import os
import uuid
from pathlib import Path
from .adapters.huawei_b7 import validate_payload

class Outbox:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
    def enqueue(self,payload):
        validate_payload(payload,require_recent=False)
        target=self.path/(uuid.uuid4().hex+'.json');temporary=target.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8') as handle:
            json.dump(payload,handle,ensure_ascii=False,allow_nan=False);handle.flush();os.fsync(handle.fileno())
        temporary.replace(target)
        return target
    def flush(self,send):
        accepted=0
        for path in sorted(self.path.glob('*.json'),key=lambda p:p.stat().st_mtime_ns):
            payload=json.loads(path.read_text(encoding='utf-8'));validate_payload(payload,require_recent=False)
            send(payload)
            # This exact file was acknowledged; no recursive clean-up or age deletion.
            path.unlink();accepted+=1
        return accepted
    def pending(self):return sum(1 for _ in self.path.glob('*.json'))
