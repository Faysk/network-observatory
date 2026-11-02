"""Bounded login recovery. The private ledger contains no session or credentials."""
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path


class RecoveryWait(Exception):
    def __init__(self, reason, seconds, blocked=False):
        self.reason, self.seconds, self.blocked = reason, max(1, seconds), blocked
        super().__init__(reason)


class LoginRecovery:
    # Includes initial logins and renewals. Normal successful renewal once per
    # minute remains possible; failed episodes have a separate strict budget.
    DELAYS = (300, 900, 1800)
    WINDOW = 3600

    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.data = {'last_login': 0, 'failures': [], 'next_retry': 0,
                     'rejections': 0, 'blocked': False, 'reason': None}
        if self.path.exists():
            try:
                with self.path.open(encoding='utf-8') as handle:
                    value = json.loads(handle.read(8193))
                for key in ('last_login', 'next_retry'):
                    if type(value[key]) not in (int, float) or not math.isfinite(value[key]):
                        raise ValueError()
                if (type(value['rejections']) is not int or not 0 <= value['rejections'] <= 3
                        or type(value['blocked']) is not bool
                        or not isinstance(value['failures'], list) or len(value['failures']) > 3
                        or any(type(v) not in (int, float) or not math.isfinite(v)
                               for v in value['failures'])):
                    raise ValueError()
                self.data.update({k: value[k] for k in self.data if k in value})
                if self.data['reason'] not in (None, 'session_expired', 'login_rate_limited',
                        'invalid_login_challenge', 'login_failed', 'login_rejected', 'authentication_failed'):
                    raise ValueError()
            except (ValueError, KeyError, TypeError, OSError):
                # Never turn a corrupt/unreadable ledger into a fresh budget.
                self.data.update(blocked=True, reason='recovery_state_invalid')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(self.data, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def check(self):
        now = self.clock()
        if self.data['blocked']:
            raise RecoveryWait(self.data['reason'] or 'authentication_failed', 60, True)
        remaining = max(self.data['next_retry'], self.data['last_login'] + 60) - now
        if remaining > 0:
            raise RecoveryWait(self.data['reason'] or 'login_rate_limited', remaining)

    def before_login(self):
        self.check()
        # Persist before a POST. Restarting the process cannot bypass the floor.
        self.data['last_login'] = self.clock()
        self.save()

    def failure(self, reason):
        now = self.clock()
        failures = [v for v in self.data['failures'] if now - v < self.WINDOW]
        failures.append(now)
        failures = failures[-3:]
        self.data.update(failures=failures, reason=reason)
        if reason in ('login_rejected', 'login_failed'):
            self.data['rejections'] = min(3, self.data['rejections'] + 1)
        # An incompatible challenge is not safe to retry. Repeated rejected
        # logins require an operator; a 403 on a data GET is not bad credentials.
        self.data['blocked'] = reason == 'invalid_login_challenge' or self.data['rejections'] >= 3
        delay = self.DELAYS[len(failures) - 1]
        if len(failures) >= 3:
            delay = max(delay, failures[0] + self.WINDOW - now)
        self.data['next_retry'] = now + delay
        self.save()

    def success(self):
        # Keep rolling failure history across brief successes (no flapping reset).
        self.data.update(next_retry=0, reason=None, rejections=0, blocked=False)
        self.save()

    def public(self):
        value = self.data['next_retry']
        return {'next_retry_at': datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')
                if value and not self.data['blocked'] else None,
                'auth_failures_in_window': len([v for v in self.data['failures']
                                               if self.clock() - v < self.WINDOW]),
                'intervention_required': self.data['blocked']}
