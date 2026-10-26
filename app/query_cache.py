"""Bounded RAM cache and shared calculations; never persistent or authoritative."""
import copy
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future


class QueryCache:
    def __init__(self, ttl=20, entries=8, byte_limit=2*1024*1024, readers=2):
        self.ttl, self.entries, self.byte_limit = ttl, entries, byte_limit
        self.cache = OrderedDict()
        self.flights = {}
        self.bytes = 0
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(readers)

    def get(self, key, revision, compute, current_revision):
        flight_key = (key, revision)
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[1] == revision and time.monotonic()-cached[0] < self.ttl:
                self.cache.move_to_end(key)
                value = cached[2]
                leader = None
            else:
                value = None
                future = self.flights.get(flight_key)
                leader = future is None
                if leader:
                    future = Future()
                    self.flights[flight_key] = future
        if leader is None:
            return copy.deepcopy(value)
        if leader:
            try:
                with self.slots:
                    result = compute()
                size = len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                if size <= self.byte_limit and current_revision() == revision:
                    with self.lock:
                        old = self.cache.pop(key, None)
                        if old:
                            self.bytes -= old[3]
                        self.cache[key] = (time.monotonic(), revision, result, size)
                        self.bytes += size
                        while len(self.cache) > self.entries or self.bytes > self.byte_limit:
                            _, evicted = self.cache.popitem(last=False)
                            self.bytes -= evicted[3]
                future.set_result(result)
            except BaseException as exc:
                future.set_exception(exc)
                raise
            finally:
                with self.lock:
                    self.flights.pop(flight_key, None)
        return copy.deepcopy(future.result())
