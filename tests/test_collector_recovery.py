"""Synthetic recovery and ambiguous-ack tests. No production or router access."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import core
from app.collector_recovery import LoginRecovery, RecoveryWait
from app.adapters import huawei_b7 as h
from app.outbox import Outbox
from app.server import Handler
from test_huawei import payload, fixture
from datetime import datetime, timezone, timedelta


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'recovery.json'
        self.now = 10000
        self.policy = LoginRecovery(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_cannot_bypass_login_floor_or_failure_cooldown(self):
        self.policy.before_login()
        restarted = LoginRecovery(self.path, clock=lambda: self.now)
        with self.assertRaises(RecoveryWait) as wait:
            restarted.before_login()
        self.assertEqual(wait.exception.seconds, 60)
        self.assertIsNotNone(restarted.public()['next_retry_at'])
        self.policy.failure('session_expired')
        restarted = LoginRecovery(self.path, clock=lambda: self.now)
        with self.assertRaises(RecoveryWait) as wait:
            restarted.check()
        self.assertEqual(wait.exception.seconds, 300)
        self.now += 300
        restarted.before_login()

    def test_rolling_budget_includes_failures_across_brief_successes(self):
        times = []
        for _ in range(4):
            self.policy.check()
            times.append(self.now)
            self.policy.failure('session_expired')
            self.now = self.policy.data['next_retry']
            self.policy.success()
        self.assertEqual(times[:4], [10000, 10300, 11200, 13600])
        self.assertFalse(self.policy.data['blocked'])

    def test_repeated_rejected_logins_block_but_expired_sessions_recover(self):
        for _ in range(3):
            self.policy.failure('login_rejected')
            self.now = self.policy.data['next_retry']
        self.assertTrue(self.policy.public()['intervention_required'])
        restarted = LoginRecovery(self.path, clock=lambda: self.now)
        with self.assertRaises(RecoveryWait) as wait:
            restarted.check()
        self.assertTrue(wait.exception.blocked)
        self.assertIsNone(restarted.public()['next_retry_at'])

    def test_incompatible_challenge_and_corrupt_ledger_fail_closed(self):
        self.policy.failure('invalid_login_challenge')
        self.assertTrue(self.policy.data['blocked'])
        for invalid in ('{', '{}', '{"failures": [NaN]}'):
            self.path.write_text(invalid)
            restarted = LoginRecovery(self.path)
            with self.assertRaises(RecoveryWait): restarted.before_login()
            self.assertEqual(restarted.data['reason'], 'recovery_state_invalid')

    def test_ledger_write_failure_prevents_post(self):
        adapter = h.HuaweiB7('192.168.1.1', 'synthetic-user', 'synthetic-password')
        adapter.login_recovery = self.policy
        with patch.object(self.policy, 'save', side_effect=OSError), patch.object(adapter, '_request') as request:
            with self.assertRaises(OSError): adapter._login(None)
        request.assert_not_called()

    def test_authentication_codes_are_sanitized(self):
        error = h.AuthenticationError('secret-password-cookie', 'secret-challenge')
        self.assertEqual(str(error), 'authentication_failed')
        self.assertEqual(error.stage, 'data')

    def test_clock_rollback_never_accelerates_login(self):
        self.policy.before_login()
        self.now -= 100
        with self.assertRaises(RecoveryWait) as wait: self.policy.check()
        self.assertEqual(wait.exception.seconds, 160)

    def test_state_publication_never_waits_for_sqlite_lock(self):
        entered=threading.Event();release=threading.Event();published=threading.Event()
        old=core.get_collector_state()
        def reader():
            with core.LOCK:
                entered.set();release.wait(3)
        def writer():
            core.set_collector_state('ok',last_persisted_at='synthetic')
            snapshot=core.get_collector_state()
            snapshot['state']='must not mutate shared state'
            if core.get_collector_state()['state']=='ok':published.set()
        a=threading.Thread(target=reader);b=threading.Thread(target=writer)
        a.start()
        try:
            self.assertTrue(entered.wait(1));b.start()
            self.assertTrue(published.wait(1),'state publication waited for a database reader')
        finally:
            release.set();a.join(3)
            if b.ident is not None:b.join(3)
            core.COLLECTOR_STATE.clear();core.COLLECTOR_STATE.update(old)

    def test_http_rejection_stage_is_preserved(self):
        adapter = h.HuaweiB7('192.168.1.1', 'fixture', 'fixture')
        for route, stage, code in [('/login.cgi','login','login_rejected'),
                ('/asp/GetRandCount.asp','challenge','session_expired'),
                ('/index.asp','data','session_expired')]:
            conn = MagicMock(); response = conn.getresponse.return_value
            response.status = 403; response.read.return_value = b'private synthetic response'
            with self.assertRaises(h.AuthenticationError) as caught:
                adapter._request(conn, 'GET' if stage=='data' else 'POST', route)
            self.assertEqual((caught.exception.stage, caught.exception.code), (stage, code))
            self.assertEqual(caught.exception.http_status, 403)

    def test_new_login_is_not_replayed_in_same_cycle(self):
        adapter = h.HuaweiB7('192.168.1.1','fixture','fixture')
        adapter.verified_model = 'HG8247B7-8N'; adapter.cached = payload()
        with patch.object(adapter, '_login') as login, patch.object(adapter, '_read_data',
                side_effect=h.AuthenticationError('session_expired')):
            with self.assertRaises(h.AuthenticationError): adapter.collect()
            self.assertEqual(login.call_count, 1)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_state = dict(core.COLLECTOR_STATE)
        self.db_patch = patch.object(core, 'DB_PATH', Path(self.temp.name)/'test.db')
        self.db_patch.start(); core.init_db()

    def tearDown(self):
        core.COLLECTOR_STATE.clear(); core.COLLECTOR_STATE.update(self.old_state)
        self.db_patch.stop(); self.temp.cleanup()

    def test_commit_then_lost_ack_replay_is_idempotent_and_conflict_rejected(self):
        sample = payload()
        _, stations, _ = h.parse_stations(fixture('stations'))
        sample.update(stations=stations, clients=h.parse_clients(fixture('stations'),stations,fixture('lan')))
        sample['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
        core.put_huawei_sample(sample)
        sample=json.loads(json.dumps(sample))
        sample.update(collected_at=datetime.now(timezone.utc).isoformat(),stations=[])
        sample['clients'][0]['reported_status']='Offline'
        box = Outbox(core.DB_PATH.parent/'outbox'); box.enqueue(sample)
        def lost_ack(value):
            core.put_huawei_sample(value)
            raise BrokenPipeError('synthetic lost acknowledgement')
        with self.assertRaises(BrokenPipeError): box.flush(lost_ack)
        self.assertEqual(box.pending(), 1)
        with core.connect() as db:
            before = {table: db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                      for table in ('huawei_samples','router_client_samples','events','router_observations',
                                    'router_chart_points','client_chart_points','history_versions')}
        self.assertEqual(before['events'], 1)
        self.assertEqual(before['client_chart_points'], 2)
        box.flush(core.put_huawei_sample)
        self.assertEqual(box.pending(), 0)
        with core.connect() as db:
            after = {table: db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in before}
        self.assertEqual(before, after)
        conflict = dict(sample, metrics={})
        with self.assertRaises(ValueError): core.put_huawei_sample(conflict)

    def test_integrated_delivery_has_no_http_deadline_and_confirms_commit(self):
        adapter = MagicMock(); adapter.clock.return_value = 10000; adapter.next_attempt = 0
        sample = payload(); adapter.collect.return_value = sample
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('no loopback HTTP')):
            h.run_collector(adapter, 1, 'x'*32, False, keep_serving_on_auth_error=True)
        self.assertEqual(core.COLLECTOR_STATE['state'], 'ok')
        self.assertEqual(core.COLLECTOR_STATE['last_persisted_at'], sample['collected_at'])
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM huawei_samples').fetchone()[0], 1)

    def test_auth_cooldown_does_not_block_pending_delivery(self):
        box = Outbox(core.DB_PATH.parent/'outbox'); box.enqueue(payload())
        policy = LoginRecovery(core.DB_PATH.parent/'collector-recovery.json')
        policy.failure('session_expired')
        adapter = MagicMock()
        with patch('app.adapters.huawei_b7.time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                h.run_collector(adapter, 1, 'x'*32, True, keep_serving_on_auth_error=True)
        adapter.collect.assert_not_called()
        self.assertEqual(box.pending(), 0)
        self.assertEqual(core.COLLECTOR_STATE['state'], 'auth_backoff')

    def test_watch_recovers_session_without_restarting_or_early_login(self):
        now = [10000]
        policy = LoginRecovery(core.DB_PATH.parent/'collector-recovery.json', clock=lambda: now[0])
        adapter = MagicMock(); adapter.next_attempt = 0; adapter.clock.side_effect = lambda: now[0]
        sample = payload()
        adapter.collect.side_effect = [h.AuthenticationError('session_expired'), sample, KeyboardInterrupt]
        attempted = []
        def sleep(seconds):
            attempted.append((now[0], adapter.collect.call_count))
            now[0] += seconds
        with patch('app.collector_recovery.LoginRecovery', return_value=policy), patch(
                'app.adapters.huawei_b7.time.sleep', side_effect=sleep):
            with self.assertRaises(KeyboardInterrupt):
                h.run_collector(adapter, 1, 'x'*32, True, keep_serving_on_auth_error=True)
        self.assertEqual(adapter.collect.call_count, 3)
        self.assertTrue(all(count == 1 for stamp, count in attempted if stamp < 10300))
        self.assertEqual(core.COLLECTOR_STATE['last_success'], sample['collected_at'])
        self.assertEqual(Outbox(core.DB_PATH.parent/'outbox').pending(), 0)

    def test_local_login_floor_does_not_consume_failure_budget(self):
        adapter = MagicMock(); adapter.next_attempt=0; adapter.clock.return_value=10000
        adapter.collect.side_effect=h.AuthenticationError('login_rate_limited','login')
        with patch('app.adapters.huawei_b7.time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                h.run_collector(adapter, 1, 'x'*32, True, keep_serving_on_auth_error=True)
        self.assertEqual(core.COLLECTOR_STATE['auth_failures_in_window'], 0)
        self.assertEqual(core.COLLECTOR_STATE['state'], 'auth_backoff')

    def test_broken_response_after_commit_never_sends_second_response(self):
        handler = Handler.__new__(Handler)
        handler.path = '/api/ingest/huawei'; handler.client_address = ('127.0.0.1', 1)
        sample = payload(); body = json.dumps(sample).encode()
        handler.headers = {'Content-Length': str(len(body))}; handler.rfile = io.BytesIO(body)
        handler.validate_host = lambda: True; handler.authenticate_write = lambda: True
        handler.respond = MagicMock(side_effect=BrokenPipeError)
        handler.error_json = MagicMock()
        with patch.object(core, 'WRITE_TOKEN', 'synthetic-write-token-at-least-32-characters'):
            handler.do_POST()
        handler.respond.assert_called_once(); handler.error_json.assert_not_called()
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM huawei_samples').fetchone()[0], 1)
