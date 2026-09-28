"""Offline packaged-executable protocol check; loopback only, no robot or secrets."""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace


async def check():
    from esptool.loader import StubFlasher
    assert len(StubFlasher('esp32s3').text)>1000
    from websockets.asyncio.client import connect
    from .remote_server import RemoteServer
    with tempfile.TemporaryDirectory() as directory:
        c=SimpleNamespace(app=None,emit=lambda *a:None,services=SimpleNamespace(paths=SimpleNamespace(root=Path(directory))))
        server=RemoteServer(c);server.pairing={'key':'ac'*32,'device_id':'34'*8}
        await server.listen('127.0.0.1',0)
        try:
            async with connect(f'ws://127.0.0.1:{server.port}/kadence/v1',proxy=None) as ws:
                challenge=json.loads(await ws.recv());device=server.pairing['device_id']
                proof=hmac.new(bytes.fromhex(server.pairing['key']),f"1:{challenge['nonce']}:{device}".encode(),hashlib.sha256).hexdigest()
                await ws.send(json.dumps({'v':1,'type':'remote.hello','device':'StickS3','device_id':device,'proof':proof}))
                assert json.loads(await ws.recv())['type']=='remote.accept'
                value=json.loads(await ws.recv())
                assert value['robot_link']=='tethered' and value['capabilities']['gyro'] is False
                await ws.send(json.dumps({'v':1,'seq':1,'type':'audio.start'}))
                while True:
                    value=json.loads(await ws.recv())
                    if value['type']=='remote.result':break
                assert value['ok'] is False and value['message']=='Robot is disconnected.'
        finally:await server.close()
    return {'paired_websocket':True,'robot_link':'tethered','disconnected_ptt_rejected':True,'clean_close':True}
