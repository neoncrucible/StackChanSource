"""Two preloaded, single-use speech children; no network or audio while idle."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
from .voice_providers import VoiceProviderUnavailable


async def reap(process):
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    await process.wait()


class SpeechWorkers:
    def __init__(self, command, environment, *, count=2):
        self.command = [*command, '--warm-speech']
        self.environment = environment
        self.loop = asyncio.get_running_loop()
        self.count = count
        self.waiting = []
        self.closed = False
        self.refill()

    def refill(self):
        while not self.closed and len(self.waiting) < self.count:
            task = asyncio.create_task(self.prepare(), name='kadence-speech-warmup')
            # Failure is consumed on take/close; avoid an unobserved task error.
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            self.waiting.append(task)

    async def prepare(self):
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(*self.command,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=self.environment, limit=2048, **options))
        process = None
        try:
            process = await asyncio.shield(spawning)
            async with asyncio.timeout(12):
                if json.loads(await process.stdout.readline()) != {'ready': True}:
                    raise VoiceProviderUnavailable('Speech child warm-up failed')
            return process
        except BaseException as exc:
            if process is None:
                with contextlib.suppress(Exception):
                    process = await spawning
            if process is not None:
                await reap(process)
            if isinstance(exc,asyncio.CancelledError): raise
            raise VoiceProviderUnavailable('Speech child could not preload') from exc

    async def take(self):
        if self.closed:
            raise VoiceProviderUnavailable('Speech workers are closed')
        task = self.waiting.pop(0)
        try:
            process = await asyncio.shield(task)
        except BaseException:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                process = await task
                await reap(process)
            raise
        finally:
            self.refill()
        # The caller owns and reaps this child after exactly one utterance.
        return process

    async def close(self):
        self.closed = True
        waiting, self.waiting = self.waiting, []
        for task in waiting:
            if not task.done():
                task.cancel()
        for task in waiting:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reap(await task)
