import contextlib
import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from kcore.unitv2_network import capture_jpeg, start_camera_stream

JPEG = b'\xff\xd8test\xff\xd9'
PART = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + JPEG


@contextlib.contextmanager
def server(body=PART, content_type='multipart/x-mixed-replace; boundary=frame', stall=False, needs_start=False, start_status=200, root_status=200, root_body=b"<html></html>"):
    started = False
    bootstrapped = False
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal started
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            expected = {"type_id": "3", "type_name": "camera_stream", "args": ""}
            valid = bootstrapped and self.path == '/func' and payload == expected
            started = valid and start_status == 200
            self.send_response(start_status if valid else 400)
            self.end_headers()

        def do_GET(self):
            nonlocal bootstrapped
            if self.path == '/':
                bootstrapped = root_status == 200
                self.send_response(root_status)
                self.send_header('Content-Length', str(len(root_body)))
                self.end_headers()
                try:
                    self.wfile.write(root_body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if needs_start and not started:
                self.send_response(503)
                self.end_headers()
                return
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

    def test_cold_camera_starts_without_browser(self):
        with server(needs_start=True) as port:
            with self.assertRaises(ValueError):
                capture_jpeg('127.0.0.1', port=port)
            start_camera_stream('127.0.0.1', port=port)
            for _ in range(3):
                self.assertEqual(capture_jpeg('127.0.0.1', port=port), JPEG)

    def test_startup_error_is_not_readiness(self):
        with server(start_status=500) as port:
            with self.assertRaisesRegex(ValueError, 'startup returned HTTP 500'):
                start_camera_stream('127.0.0.1', port=port)

    def test_bootstrap_http_failure(self):
        with server(root_status=500) as port:
            with self.assertRaisesRegex(ValueError, 'bootstrap returned HTTP 500'):
                start_camera_stream('127.0.0.1', port=port)

    def test_bootstrap_size_limit(self):
        with server(root_body=b'x' * (256 * 1024 + 1)) as port:
            with self.assertRaisesRegex(ValueError, 'bootstrap response exceeds limit'):
                start_camera_stream('127.0.0.1', port=port)

    def test_windows_closed_socket_after_content_length(self):
        original = socket.socket.settimeout
        def windows_settimeout(sock, value):
            if sock.fileno() == -1:
                raise OSError(10038, "An operation was attempted on something that is not a socket")
            return original(sock, value)
        with server(needs_start=True) as port:
            with patch.object(socket.socket, 'settimeout', windows_settimeout):
                start_camera_stream('127.0.0.1', port=port)
                self.assertEqual(capture_jpeg('127.0.0.1', port=port), JPEG)
