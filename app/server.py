"""LAN-first dashboard HTTP API. No root, no third-party Python dependencies."""
import argparse
import gzip
import hashlib
from functools import lru_cache
from email.utils import formatdate, parsedate_to_datetime
import csv
import io
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote
from . import core, request_timing

STATIC = Path(__file__).resolve().parent / "static"
VALT = STATIC.parent.parent / "sites" / "valt"

# Disposable in-memory cache for public code only. No API or Vault files.
@lru_cache(maxsize=16)
def _code_asset(path, mtime_ns, size):
    raw=Path(path).read_bytes()
    etag='"'+hashlib.sha256(raw).hexdigest()+'"'
    compressed=gzip.compress(raw,compresslevel=5,mtime=0) if len(raw)>=1024 and Path(path).suffix in ('.js','.css','.svg') else None
    if compressed is not None and len(compressed)>=len(raw)*0.90:compressed=None
    return raw,compressed,etag

def _accepts_gzip(value):
    for token in (value or '').lower().split(','):
        name,_,params=token.strip().partition(';')
        if name!='gzip':continue
        for part in params.split(';'):
            if part.strip().startswith('q='):
                try:return float(part.strip()[2:])>0
                except ValueError:return False
        return True
    return False



class Handler(BaseHTTPRequestHandler):
    server_version = "FayskNOC/0.1"

    def respond(self, code, data, mime="application/json; charset=utf-8"):
        with request_timing.phase('serialize'):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            if isinstance(body, str): body = body.encode()
        is_api = urlsplit(self.path).path.startswith('/api/')
        packed = None
        if is_api and len(body) >= 16384 and _accepts_gzip(self.headers.get('Accept-Encoding')):
            with request_timing.phase('compress'):
                candidate = gzip.compress(body, compresslevel=1, mtime=0)
                if len(candidate) < len(body)*0.9: packed = candidate
        if packed is not None: body = packed
        self.send_response(code)
        if is_api:
            timing = request_timing.header()
            if timing: self.send_header('Server-Timing', timing)
            self.send_header('Vary', 'Accept-Encoding')
            if packed is not None: self.send_header('Content-Encoding', 'gzip')
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN" if urlsplit(self.path).path.startswith("/valt/") else "DENY")
        style_policy = " 'unsafe-inline'" if urlsplit(self.path).path.startswith("/s7/") else ""
        self.send_header("Content-Security-Policy", "default-src 'self' data: blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' data: blob:; object-src 'self' data: blob:; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'" if urlsplit(self.path).path.startswith("/valt/") else "default-src 'self'; img-src 'self' data:; style-src 'self'" + style_policy + "; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if not getattr(self,'_head_only',False):self.wfile.write(body)

    def static_code(self, target, mime):
        stat=target.stat()
        raw,packed,raw_tag=_code_asset(str(target),stat.st_mtime_ns,stat.st_size)
        use_gzip=packed is not None and _accepts_gzip(self.headers.get('Accept-Encoding'))
        # Strong ETags are representation-specific: gzip bytes != identity bytes.
        etag=raw_tag[:-1]+('-gzip' if use_gzip else '-identity')+'"'
        modified=formatdate(stat.st_mtime,usegmt=True)
        match=self.headers.get('If-None-Match')
        valid=match is not None and any(tag.strip()=='*' or tag.strip().removeprefix('W/')==etag for tag in match.split(','))
        if match is None and self.headers.get('If-Modified-Since'):
            try:
                parsed=parsedate_to_datetime(self.headers['If-Modified-Since'])
                # HTTP-date has whole-second precision, including mtimes ending .9999.
                valid=parsed.tzinfo is not None and int(stat.st_mtime)<=int(parsed.timestamp())
            except (ValueError,TypeError,OverflowError):pass
        body=packed if use_gzip else raw
        self.send_response(304 if valid else 200)
        self.send_header('ETag',etag)
        self.send_header('Last-Modified',modified)
        self.send_header('Vary','Accept-Encoding')
        self.send_header('Cache-Control','private, no-cache, must-revalidate')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if use_gzip and not valid:self.send_header('Content-Encoding','gzip')
        if not valid:
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        if not valid and not getattr(self,'_head_only',False):self.wfile.write(body)

    def do_HEAD(self):
        self._head_only=True
        try:
            with request_timing.request_scope():self.get_response()
        finally:self._head_only=False

    def error_json(self, code, message):
        self.respond(code, {"error": message})

    def authenticate_write(self):
        """All mutations require FNO_INGEST_TOKEN, even on localhost."""
        token = core.WRITE_TOKEN
        if not token:
            self.error_json(403, "Escrita desativada. Define FNO_INGEST_TOKEN no ambiente e reinicia.")
            return False
        from hmac import compare_digest
        candidate = self.headers.get("X-API-Key", "")
        if not compare_digest(candidate, token):
            self.error_json(401, "X-API-Key inválida")
            return False
        origin = self.headers.get("Origin")
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            host = self.headers.get("Host", "")
            if parsed.netloc != host or parsed.scheme not in ("http", "https"):
                self.error_json(403, "Origem inválida")
                return False
        return True

    def do_GET(self):
        from . import host_telemetry
        began = time.perf_counter()
        try:
            with request_timing.request_scope():
                return self.get_response()
        finally:
            host_telemetry.record_api(urlsplit(self.path).path, (time.perf_counter()-began)*1000)

    def get_response(self):
        path = urlsplit(self.path)
        if path.scheme or path.netloc:
            return self.error_json(403, 'Proxy requests are not supported')
        try:
            if path.path in ('/', '/router', '/s7', '/valt'):
                destination = '/router/' if path.path == '/' else path.path + '/'
                self.send_response(302); self.send_header('Location', destination); self.end_headers(); return
            if path.path.startswith('/valt/'):
                relative = unquote(path.path[len('/valt/'):]) or 'index.html'
                if '..' in Path(relative).parts or '\\' in relative:
                    return self.error_json(403, 'Invalid path')
                target = (VALT / relative).resolve()
                if not target.is_relative_to(VALT.resolve()) or not target.is_file():
                    return self.error_json(404, 'Not found')
                return self.respond(200, target.read_bytes(), mimetypes.guess_type(target)[0] or 'application/octet-stream')
            if path.path in ('/api/host/snapshot', '/api/host/history', '/api/host/archive', '/api/host/catalog'):
                from . import host_telemetry
                monitor = host_telemetry._monitor
                if monitor is None: return self.error_json(503, 'Telemetria do host não iniciada')
                if path.path.endswith('/snapshot'): return self.respond(200, monitor.snapshot())
                query = parse_qs(path.query)
                if path.path.endswith('/catalog'): return self.respond(200, monitor.catalog())
                if path.path.endswith('/archive'): return self.respond(200, monitor.archive(query.get('after',[0])[0],query.get('limit',[100])[0]))
                return self.respond(200, monitor.history(query.get('metric',['cpu'])[0], query.get('range',['24h'])[0]))
            if path.path == '/api/v1/overview':
                from .historian import overview_history
                return self.respond(200,overview_history(parse_qs(path.query).get('period',['24h'])[0],parse_qs(path.query).get('view',['full'])[0]))
            if path.path.startswith('/api/v1/devices/'):
                from .historian import device_history
                parts=path.path.strip('/').split('/')
                if len(parts) not in (4,5):return self.error_json(404,'Not found')
                query=parse_qs(path.query);period=query.get('period',['24h'])[0]
                if len(parts)==5:
                    if parts[4] not in ('export.csv','export.json'):return self.error_json(404,'Not found')
                    return self.export_device(parts[3],period,parts[4])
                try:return self.respond(200,device_history(parts[3],period))
                except LookupError:return self.error_json(404,'Device not found')
            if path.path == "/api/status": return self.respond(200, core.get_status())
            if path.path == '/api/router/observability':
                from .router_observability import read
                hours=float(parse_qs(path.query).get('hours',[24])[0])
                with core.LOCK,core.connect() as db:
                    result=read(db,hours)
                return self.respond(200,result)
            if path.path == '/api/router/observability/trend':
                from .router_observability import trend
                query=parse_qs(path.query)
                with core.LOCK,core.connect() as db:
                    result=trend(db,query.get('source',[''])[0],query.get('hours',[24])[0],
                                 query.get('limit',[400])[0])
                return self.respond(200,result)
            if path.path == '/api/router/observability/archive':
                from .router_observability import archive
                query=parse_qs(path.query)
                with core.LOCK,core.connect() as db:
                    result=archive(db,query.get('source',[''])[0],query.get('after',[0])[0],query.get('limit',[100])[0])
                return self.respond(200,result)
            if path.path == '/api/router/observability/change':
                from .router_observability import read_change
                with core.LOCK,core.connect() as db:
                    result=read_change(db,parse_qs(path.query).get('id',[0])[0])
                return self.respond(200,result) if result else self.error_json(404,'Change not found')
            if path.path == '/api/archive':
                query=parse_qs(path.query)
                return self.respond(200,core.get_archive(query.get('kind',['huawei'])[0],
                    query.get('after',[0])[0],query.get('limit',[1000])[0]))
            if path.path == "/api/history":
                hours = max(1, min(24*30, int(parse_qs(path.query).get("hours", [24])[0])))
                return self.respond(200, core.get_history(hours))
            if path.path == '/api/router/clients':
                query=parse_qs(path.query)
                return self.respond(200,core.get_router_clients(query.get('mac',[None])[0],query.get('limit',[120])[0]))
            if path.path == "/api/devices":
                with core.LOCK, core.connect() as db:
                    return self.respond(200, core.list_devices(db))
            if path.path == "/api/events":
                return self.respond(200, core.get_events())
            if path.path == "/api/capabilities":
                return self.respond(200, {"confirmed":["gateway tcp reachability","external tcp probe","sqlite history","event transitions","manual devices","passive neighbor cache","prometheus metrics"],
                    "requires_adapter":["cpu","memory","uptime","wan traffic","wifi clients","optic status","router system logs"],
                    "unavailable_without_access":["per-client WAN bandwidth","deep packet inspection","wifi spectral analysis","router OS logs if not exposed"],
                    "source":"capability matrix, not actual readings"})
            if path.path == "/api/neighbors": return self.respond(200, core.passive_neighbors())
            if path.path == "/metrics": return self.respond(200, core.metrics_text(), "text/plain; version=0.0.4; charset=utf-8")
            if path.path == "/api/export/events.csv":
                events = core.get_events(limit=100000)
                f = io.StringIO(); w = csv.DictWriter(f, fieldnames=["id","ts","severity","category","title","detail","source"])
                w.writeheader(); w.writerows(events)
                return self.respond(200, "\ufeff"+f.getvalue(), "text/csv; charset=utf-8")
            relative = "index.html" if path.path in ("", "/router/") else "s7/index.html" if path.path == "/s7/" else path.path[len("/router/"):] if path.path.startswith("/router/") else path.path.lstrip("/")
            if ".." in Path(relative).parts: return self.error_json(403, "Invalid path")
            fpath = (STATIC / relative).resolve()
            if not fpath.is_relative_to(STATIC.resolve()) or not fpath.is_file():
                return self.error_json(404, "Not found")
            content_type = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
            if fpath.suffix.lower() in ('.js','.css','.svg','.woff2') and fpath.stat().st_size<=512*1024:
                return self.static_code(fpath,content_type)
            return self.respond(200, fpath.read_bytes(), content_type)
        except (ValueError, TypeError) as exc:
            return self.error_json(400, str(exc))
        except Exception as exc:
            print("Request failure:", repr(exc))
            return self.error_json(500, "Internal error")

    def export_device(self,identifier,period,format_name):
        """Stream every raw observation in the selected window, without a chart limit."""
        from .historian import device_mac,window,sample
        mac=device_mac(identifier);start,end=window(period)
        with core.connect() as db:
            if not db.execute('SELECT 1 FROM router_client_samples WHERE mac=? LIMIT 1',(mac,)).fetchone():
                return self.error_json(404,'Device not found')
            rows=db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? AND ts>=? AND ts<=? ORDER BY ts,id',(mac,start.isoformat(),end.isoformat()))
            self.send_response(200)
            is_csv=format_name.endswith('.csv')
            self.send_header('Content-Type','text/csv; charset=utf-8' if is_csv else 'application/json; charset=utf-8')
            self.send_header('Content-Disposition',f'attachment; filename="faysk-{identifier}-{period}.{format_name.split(".")[-1]}"')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Connection','close');self.end_headers();self.close_connection=True
            fields=('timestamp','online','rssi_dbm','snr_db','link_rx_phy_mbps','link_tx_phy_mbps','download_mbps','upload_mbps','latency_lan_ms','interface','source','quality','measurement_semantics','observation_json')
            def csv_line(values):
                buf=io.StringIO();csv.writer(buf).writerow(values);self.wfile.write(buf.getvalue().encode('utf-8'))
            if is_csv:
                self.wfile.write(b'\xef\xbb\xbf');csv_line(fields)
            else:self.wfile.write(b'[')
            first=True
            for row in rows:
                payload=json.loads(row['payload']);point=sample(row['ts'],payload)
                if is_csv:
                    point['observation_json']=json.dumps(payload,ensure_ascii=False,allow_nan=False)
                    csv_line([point.get(k) for k in fields])
                else:
                    if not first:self.wfile.write(b',')
                    self.wfile.write(json.dumps({'collected_at':row['ts'],'source':'huawei-b7-http','observation':payload,'measurement':point},ensure_ascii=False,allow_nan=False).encode('utf-8'))
                first=False
            if not is_csv:self.wfile.write(b']')

    def do_POST(self):
        if not self.authenticate_write(): return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= (262144 if urlsplit(self.path).path == '/api/ingest/huawei' else 32768):
                return self.error_json(413, "Payload too large")
            data = json.loads(self.rfile.read(size) or b"{}")
            path = urlsplit(self.path).path
            if path == '/api/ingest/huawei':
                if len(core.WRITE_TOKEN) < 32:
                    return self.error_json(403, 'Token de ingestão requer pelo menos 32 caracteres')
                core.put_huawei_sample(data,historical=self.headers.get('X-FNO-Backfill')=='1')
                return self.respond(201, {'ok': True})
            if path == "/api/ingest/router":
                if not isinstance(data, dict): raise ValueError("JSON object expected")
                metrics = core.put_router_metrics(data.get("metrics", {}), str(data.get("source", "external-adapter")))
                return self.respond(201, {"ok": True, "accepted": list(metrics)})
            if path == "/api/devices":
                core.add_device(data)
                return self.respond(201, {"ok": True})
            if path == "/api/devices/delete":
                core.delete_device(int(data.get("id", -1)))
                return self.respond(200, {"ok": True})
            return self.error_json(404, "Unknown endpoint")
        except (ValueError, TypeError) as exc:
            return self.error_json(400, str(exc))
        except Exception as exc:
            print("Mutation failed:", repr(exc))
            return self.error_json(500, "Internal error")


def main():
    parser = argparse.ArgumentParser(description="Faysk Network Observatory")
    parser.add_argument("--host", default=os.environ.get("FNO_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FNO_PORT", "8765")))
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: listening on a non-loopback interface. The read API has no login; use a trusted VPN/reverse proxy.")
    core.init_db()
    stop = threading.Event()
    worker = threading.Thread(target=core.collector_loop, args=(stop,), daemon=True)
    worker.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    from . import host_telemetry
    host_telemetry.start(core.DB_PATH, args.port)
    print(f"Faysk NOC running at http://{args.host}:{args.port} (interval {core.INTERVAL}s)")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); server.server_close()

if __name__ == "__main__": main()

