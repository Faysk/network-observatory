"""Durable, private local outbox. Payloads only; never credentials or session data."""
import json
import os
import uuid
from pathlib import Path
from .adapters.huawei_b7 import validate_payload

class Outbox:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.last_quarantined=0

    def enqueue(self,payload):
        validate_payload(payload,require_recent=False)
        target=self.path/(uuid.uuid4().hex+'.json');temporary=target.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8') as handle:
            json.dump(payload,handle,ensure_ascii=False,allow_nan=False);handle.flush();os.fsync(handle.fileno())
        temporary.replace(target)
        return target

    def flush(self,send):
        """Keep unacknowledged data; isolate only unreadable/invalid queue entries.

        Invalid bytes are preserved in the same microSD-backed directory tree,
        never deleted or sent. A transport failure still stops delivery and
        leaves the pending file untouched so it can be retried.
        """
        accepted=0
        self.last_quarantined=0
        for path in sorted(self.path.glob('*.json'),key=lambda p:p.stat().st_mtime_ns):
            try:
                payload=json.loads(path.read_text(encoding='utf-8'))
                validate_payload(payload,require_recent=False)
            except (ValueError,TypeError,KeyError,UnicodeError):
                rejected=self.path/'quarantine'
                rejected.mkdir(mode=0o700,exist_ok=True)
                # Never replace an existing quarantined sample with the same
                # basename. mkdir is exclusive, including between processes.
                # The rename is on the same configured volume; a failed move
                # leaves the original queue file unacknowledged.
                for _ in range(12):
                    unique=rejected/uuid.uuid4().hex
                    try:unique.mkdir(mode=0o700)
                    except FileExistsError:continue
                    try:path.rename(unique/path.name)
                    except OSError:
                        try:unique.rmdir()
                        except OSError:pass
                        raise
                    break
                else:raise OSError('quarantine_slot_collision')
                self.last_quarantined+=1
                continue
            send(payload)
            # Only a positively acknowledged message is deleted.
            path.unlink();accepted+=1
        return accepted

    def pending(self):return sum(1 for _ in self.path.glob('*.json'))
    def quarantined(self):
        folder=self.path/'quarantine'
        return sum(1 for _ in folder.rglob('*.json')) if folder.is_dir() else 0
