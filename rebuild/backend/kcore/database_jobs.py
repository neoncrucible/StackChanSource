"""Keep cancelled SQLite jobs owned until their worker closes the connection."""
import asyncio


class DatabaseJobs:
    def __init__(self):
        self.pending = set()
        self.closed = False

    async def run(self, function, *args, **kwargs):
        if self.closed: raise RuntimeError("Local database is closing.")
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self.pending.add(task)
        task.add_done_callback(self._finished)
        # Cancelling a caller cannot stop a SQLite thread or roll back a write
        # already committed. Retain the task so shutdown can wait for it.
        return await asyncio.shield(task)

    def _finished(self, task):
        self.pending.discard(task)
        if not task.cancelled(): task.exception()

    async def close(self):
        self.closed = True
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)
