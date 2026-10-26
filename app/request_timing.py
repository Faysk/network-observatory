"""Request-scoped timings only; no SQL, parameters, identifiers or disk logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import sqlite3
import time

_current = ContextVar('request_timing', default=None)

@contextmanager
def request_scope():
    values = {'started': time.perf_counter(), 'db': 0.0, 'wait': 0.0}
    token = _current.set(values)
    try:
        yield values
    finally:
        _current.reset(token)

@contextmanager
def phase(name):
    values = _current.get()
    if values is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        values[name] = values.get(name, 0.0) + (time.perf_counter()-started)*1000

@contextmanager
def acquire(lock):
    with phase('wait'):
        lock.acquire()
    try:
        yield
    finally:
        lock.release()

def db_call(fn):
    @wraps(fn)
    def measured(*args, **kwargs):
        with phase('db'):
            return fn(*args, **kwargs)
    return measured

class Cursor(sqlite3.Cursor):
    execute = db_call(sqlite3.Cursor.execute)
    executemany = db_call(sqlite3.Cursor.executemany)
    fetchone = db_call(sqlite3.Cursor.fetchone)
    fetchmany = db_call(sqlite3.Cursor.fetchmany)
    fetchall = db_call(sqlite3.Cursor.fetchall)
    __next__ = db_call(sqlite3.Cursor.__next__)

class Connection(sqlite3.Connection):
    def cursor(self, factory=Cursor):
        return super().cursor(factory)
    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)
    def executemany(self, sql, parameters):
        return self.cursor().executemany(sql, parameters)

def header():
    values = _current.get()
    if values is None:
        return None
    elapsed = (time.perf_counter()-values['started'])*1000
    # Residual includes Python construction and untimed work; not pure CPU.
    app = max(0.0, elapsed-sum(values.get(k,0) for k in ('db','wait','serialize','compress')))
    return ', '.join(f'{k};dur={v:.3f}' for k,v in (
        ('db',values['db']),('wait',values['wait']),('app',app),
        ('serialize',values.get('serialize',0)),('compress',values.get('compress',0)),('total',elapsed)))
