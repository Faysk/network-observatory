"""Local SVG device icons: synthetic contract, no external fonts/CDNs."""
import unittest
import urllib.request
import threading
from pathlib import Path
from xml.etree import ElementTree as ET
from http.server import ThreadingHTTPServer

from app.device_classifier import CATEGORIES
from app.server import Handler

ROOT=Path(__file__).resolve().parents[1]
ICON=ROOT/'app/static/device-icons.svg'
JS=ROOT/'app/static/devices.js'
CSS=ROOT/'app/static/devices.css'


class DeviceIconTests(unittest.TestCase):
    def test_local_svg_sprite_complete_and_valid(self):
        root=ET.parse(ICON).getroot()
        self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
        symbols=root.findall('{http://www.w3.org/2000/svg}symbol')
        ids={x.attrib['id'] for x in symbols}
        self.assertEqual(ids,set(CATEGORIES))
        self.assertEqual(len(ids),len(symbols))
        for symbol in symbols:
            with self.subTest(category=symbol.attrib['id']):
                self.assertEqual(symbol.attrib.get('viewBox'),'0 0 24 24')
                self.assertTrue(list(symbol))
        data=ICON.read_text(encoding='utf-8')
        for banned in ('http://www.', 'https://www.', '<script', '<image', 'onload=', '<foreignObject'):
            # Exempt only the SVG namespace in the root, not remote dependencies.
            if banned=='http://www.':
                self.assertEqual(data.count('http://www.w3.org/2000/svg'),1)
            else:self.assertNotIn(banned,data)

    def test_frontend_icon_fallback_and_accessibility(self):
        js=JS.read_text(encoding='utf-8')
        css=CSS.read_text(encoding='utf-8')
        self.assertIn("DEVICE_CATEGORIES.has(category)?category:'unknown'",js)
        self.assertIn('/device-icons.svg#',js)
        self.assertIn('aria-hidden="true"',js)
        self.assertIn('focusable="false"',js)
        self.assertIn('viewBox="0 0 24 24"',js)
        self.assertIn('Categoria sugerida',js)
        self.assertIn('identitySubtitle(c)',js)
        self.assertIn('prefers-reduced-motion:reduce',css)
        self.assertIn(':focus-visible',css)

    def test_http_serves_sprite_without_external_fetch(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_address[1])+'/device-icons.svg',timeout=4) as resp:
                self.assertEqual(resp.status,200)
                self.assertIn('image/svg+xml',resp.headers['Content-Type'])
                self.assertEqual(resp.headers['X-Content-Type-Options'],'nosniff')
                self.assertIn(b'<symbol id="smartphone"',resp.read())
        finally:
            server.shutdown();server.server_close();worker.join(3)


if __name__=='__main__':unittest.main()
