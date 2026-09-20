"""Bounded, explicit UnitV2 LAN captures; no serial access or mode changes."""
from __future__ import annotations

import http.client
import ipaddress
import time
from email.message import Message

MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 8192


def capture_jpeg(address: str, *, timeout: float = 5.0, port: int = 80) -> bytes:
    """Read the first JPEG multipart part and close. Numeric IP avoids DNS stalls."""
    address = str(ipaddress.ip_address(address))
    if not 0 < timeout <= 30:
        raise ValueError("timeout must be between 0 and 30 seconds")
    deadline = time.monotonic() + timeout
    connection = http.client.HTTPConnection(address, port, timeout=timeout)
    try:
        connection.request("GET", "/video_feed", headers={"Connection": "close"})
        # HTTP/1.0 closes connection ownership after getresponse; retain the socket
        # so every body read still uses the remaining total deadline.
        sock = connection.sock
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"UnitV2 returned HTTP {response.status}")
        mime = Message()
        mime["content-type"] = response.getheader("Content-Type", "")
        boundary = mime.get_param("boundary")
        if mime.get_content_type() != "multipart/x-mixed-replace" or not boundary:
            raise ValueError("UnitV2 did not return a multipart image stream")
        boundary = boundary.encode("ascii")
        if len(boundary) > 70 or b"\r" in boundary or b"\n" in boundary:
            raise ValueError("invalid multipart boundary")
        buffer = bytearray()
        headers_done = False
        body = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("UnitV2 frame deadline exceeded")
            sock.settimeout(remaining)
            chunk = response.read1(4096)
            if not chunk:
                raise ValueError("UnitV2 stream ended before a complete JPEG")
            if not headers_done:
                buffer.extend(chunk)
                split = buffer.find(b"\r\n\r\n")
                if split < 0:
                    if len(buffer) > MAX_HEADER_BYTES:
                        raise ValueError("multipart headers exceed limit")
                    continue
                if split > MAX_HEADER_BYTES:
                    raise ValueError("multipart headers exceed limit")
                lines = bytes(buffer[:split]).split(b"\r\n")
                while lines and not lines[0]:
                    lines.pop(0)
                if not lines or lines.pop(0) != b"--" + boundary:
                    raise ValueError("unexpected multipart boundary")
                headers = {}
                for line in lines:
                    key, sep, value = line.partition(b":")
                    if not sep:
                        raise ValueError("malformed multipart header")
                    headers[key.strip().lower()] = value.strip().lower()
                if headers.get(b"content-type") != b"image/jpeg":
                    raise ValueError("multipart part is not a JPEG")
                chunk = bytes(buffer[split + 4:])
                headers_done = True
                buffer.clear()
            body.extend(chunk)
            if len(body) >= 2 and body[:2] != b"\xff\xd8":
                raise ValueError("invalid JPEG start")
            end = body.find(b"\xff\xd9")
            if end >= 0:
                if end + 2 > MAX_FRAME_BYTES:
                    raise ValueError("JPEG exceeds frame limit")
                return bytes(body[:end + 2])
            if len(body) > MAX_FRAME_BYTES:
                raise ValueError("JPEG exceeds frame limit")
    finally:
        if "response" in locals():
            response.close()
        connection.close()
