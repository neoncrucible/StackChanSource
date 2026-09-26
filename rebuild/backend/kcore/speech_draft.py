"""Overlap private speech rendering with planning; only validated replies play."""
import asyncio
import contextlib


class _Draft:
    def __init__(self, render, text):
        self.text = text
        # The renderer bounds all PCM to 4 MiB. Only two short drafts can exist.
        self.queue = asyncio.Queue()
        async def produce():
            try:
                return await render(text, pcm_sink=self.queue.put)
            finally:
                self.queue.put_nowait(None)
        self.task = asyncio.create_task(produce(), name="kadence-speech-draft")

    async def play(self, sink):
        while True:
            # Do not start playing a draft already known to have failed.
            if self.task.done():
                self.task.result()
            chunk = await self.queue.get()
            if chunk is None:
                return await self.task
            await sink(chunk)

    async def close(self):
        if not self.task.done():
            self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self.task


class SpeechDrafts:
    def __init__(self, render):
        self.render = render
        self.first = None
        self.rest = None

    async def offer(self, text):
        if self.first is None:
            self.first = _Draft(self.render, text)

    async def speak(self, reply, sink):
        failed = self.first is not None and self.first.task.done() and (
            self.first.task.cancelled() or self.first.task.exception() is not None)
        if self.first is None or failed or not reply.startswith(self.first.text):
            await self.close()
            return await self.render(reply, pcm_sink=sink)
        # Validation has finished. Render the remainder while the buffered first
        # sentence plays, with one live output queue and original text order.
        remainder = reply[len(self.first.text):].strip()
        if remainder:
            self.rest = _Draft(self.render, remainder)
        first = await self.first.play(sink)
        rest = await self.rest.play(sink) if self.rest else b""
        return first + rest

    async def close(self):
        for draft in (self.first, self.rest):
            if draft is not None:
                await draft.close()
        self.first = self.rest = None
