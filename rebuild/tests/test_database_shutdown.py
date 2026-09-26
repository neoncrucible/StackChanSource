"""Cancellation ends the caller promptly; shutdown still owns SQLite workers."""
import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from kcore.services import LocalServices


class DatabaseShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_transaction_settles_before_services_close(self):
        with tempfile.TemporaryDirectory() as root:
            services=LocalServices(directory=Path(root));await services.start()
            entered=threading.Event();release=threading.Event();finished=threading.Event()
            original=services.store._call
            def delayed(action,args):
                if action=='project_add':
                    entered.set();release.wait(2)
                    try:return original(action,args)
                    finally:finished.set()
                return original(action,args)
            with patch.object(services.store,'_call',side_effect=delayed):
                caller=asyncio.create_task(services.store.call('project_add',name='Committed once'))
                await asyncio.wait_for(asyncio.to_thread(entered.wait),1)
                caller.cancel()
                with self.assertRaises(asyncio.CancelledError):await caller
                closing=asyncio.create_task(services.close())
                await asyncio.sleep(.02)
                self.assertFalse(closing.done())
                release.set();await asyncio.wait_for(closing,1)
                self.assertTrue(finished.is_set())
                self.assertFalse(services.store.jobs.pending)
                with self.assertRaises(RuntimeError):await services.store.call('project_list')
            reopened=LocalServices(directory=Path(root));await reopened.start()
            try:
                rows=await reopened.store.call('project_list')
                self.assertEqual([r['name'] for r in rows],['Committed once'])
            finally:await reopened.close()
