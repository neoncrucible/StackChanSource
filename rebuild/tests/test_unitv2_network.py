import contextlib
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from kcore.unitv2_network import capture_jpeg

JPEG = b'\xff\xd8test\xff\xd9'
PART = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + JPEG


@contextlib.contextmanager
def server(body=PART, content_type='multipart/x-mixed-replace; boundary=frame', stall=False):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                if stall:
                    time.sleep(0.3)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01})
    worker.start()
    try:
        yield httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join()


class UnitV2NetworkTests(unittest.TestCase):
    def test_split_frames_and_repeated_connections(self):
        with server(PART + b'\r\n' + PART) as port:
            for _ in range(3):
                self.assertEqual(capture_jpeg('127.0.0.1', port=port), JPEG)

    def test_rejects_html(self):
        with server(b'<html>', 'text/html') as port:
            with self.assertRaises(ValueError):
                capture_jpeg('127.0.0.1', port=port)

    def test_truncated(self):
        with server(PART[:-2]) as port:
            with self.assertRaises(ValueError):
                capture_jpeg('127.0.0.1', port=port)

    def test_frame_limit(self):
        with server() as port, patch('kcore.unitv2_network.MAX_FRAME_BYTES', 4):
            with self.assertRaises(ValueError):
                capture_jpeg('127.0.0.1', port=port)

    def test_stalled_body_deadline(self):
        with server(PART[:-2], stall=True) as port:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                capture_jpeg('127.0.0.1', port=port, timeout=0.1)
            self.assertLess(time.monotonic() - start, 0.25)

    def test_rejects_non_numeric_address(self):
        with self.assertRaises(ValueError):
            capture_jpeg('example.com')
