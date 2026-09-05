from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .protocol import Envelope, MessageKind

if TYPE_CHECKING:
    from .host import HostServer


async def send_voice_cancel(host: "HostServer", *, timeout: float = 3.0) -> Envelope:
    """Pre-empt an active voice turn without waiting for the body command lock.

    This is intentionally the only physical command allowed to bypass
    HostServer._command_lock: its purpose is to terminate work that currently
    owns that lock. Serial writes still pass through HostServer._write_lock and
    the response still uses the normal correlated pending-request machinery.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    writer = host._active_writer
    session = host._active_session
    if writer is None or session is None or not session.hello_seen:
        raise RuntimeError("body endpoint is not ready")

    command = Envelope(MessageKind.COMMAND, "voice.cancel", {})
    loop = asyncio.get_running_loop()
    pending: asyncio.Future[Envelope] = loop.create_future()
    if command.request_id in host._pending:
        raise RuntimeError("duplicate pending request id")
    host._pending[command.request_id] = pending
    try:
        await host._send(writer, command)
        response = await asyncio.wait_for(pending, timeout=timeout)
    except TimeoutError:
        host._retire_request(command.request_id)
        raise
    except asyncio.CancelledError:
        host._retire_request(command.request_id)
        raise
    finally:
        host._pending.pop(command.request_id, None)

    if response.kind is not MessageKind.ACK:
        raise RuntimeError(f"voice cancel expected ACK, got {response.kind.value}")
    if response.name != command.name:
        raise RuntimeError(
            f"voice cancel ACK name mismatch: expected {command.name}, got {response.name}"
        )
    if response.payload.get("ok") is not True:
        raise RuntimeError("voice cancel was not acknowledged")
    if response.payload.get("torque_released") is not True:
        raise RuntimeError("voice cancel did not prove torque release")
    return response
