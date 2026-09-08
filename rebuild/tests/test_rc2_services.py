import asyncio
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from kcore.companion import Companion
from kcore.desktop_worker import DesktopController
from kcore.services import LocalServices


class Thinker:
    def __init__(self): self.prompts=[]
    async def stream_reply(self, prompt):
        self.prompts.append(prompt)
        yield '{"reply":"Ready when you are."}'


class FakeAppliance:
    live=0
    maximum=0
    fail=False
    def __init__(self, settings, services, emit):
        self.settings=settings; self.emit=emit; self.opened=False; self.closed=False
    async def run_forever(self):
        self.opened=True; FakeAppliance.live+=1
        FakeAppliance.maximum=max(FakeAppliance.live,FakeAppliance.maximum)
        if FakeAppliance.fail: raise OSError('simulated startup failure')
        self.emit('server',{'state':'running'})
        await asyncio.Event().wait()
    async def close(self):
        if self.opened and not self.closed: FakeAppliance.live-=1
        self.closed=True


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.events=[]
        self.service=LocalServices(Path(self.temp.name),emit=lambda n,d:self.events.append((n,d)))
        await self.service.start()
    async def asyncTearDown(self):
        await self.service.close(); self.temp.cleanup()

    async def test_reads_do_not_create_refresh_feedback(self):
        project=await self.service.command('project_add',{'name':'Sensor'})
        self.events.clear()
        for _ in range(5):
            await self.service.command('entry_list',{'project_id':project['id']})
            await self.service.command('project_list',{})
        self.assertEqual(self.events,[])
        await self.service.command('utilities',{})
        self.assertEqual([e[0] for e in self.events],['utilities'])

    async def test_project_voice_lookup_uses_exact_name_without_invented_id(self):
        project=await self.service.store.call('project_add',name='Sensor bench')
        await self.service.store.call('entry_add',project_id=project['id'],kind='step',text='Measure current')
        result=await self.service.tools.execute('project_read',{'project':'sensor BENCH'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['items'][0]['text'],'Measure current')
        missing=await self.service.tools.execute('project_read',{'project':'not a project'})
        self.assertFalse(missing['ok'])

    async def test_offline_timezone_controls_clock_and_tomorrow(self):
        await self.service.command('timezone',{'timezone':'America/Los_Angeles'})
        self.service.reminders.now=lambda:datetime(2026,9,8,2,tzinfo=timezone.utc)
        response=await self.service.command('reminder_create',{'text':'check printer','when':'tomorrow at 09:00'})
        self.assertFalse(response['clarification'])
        record=(await self.service.snapshot())['reminders'][0]
        self.assertEqual(record['timezone'],'America/Los_Angeles')
        self.assertEqual(record['due'],datetime(2026,9,8,16,tzinfo=timezone.utc).timestamp())
        self.assertEqual((await self.service.snapshot())['clock']['timezone'],'America/Los_Angeles')
        with self.assertRaises(ValueError): await self.service.command('timezone',{'timezone':'invalid/zone'})

    async def test_voice_draft_only_survives_confirmed_playback(self):
        self.service.reminders.now=lambda:datetime(2026,9,7,14,tzinfo=timezone.utc)
        companion=Companion(self.service.tools,self.service.context,reminders=self.service.reminders)
        thinker=Thinker()
        question='Tomorrow remind me I need to order filament'
        reply=await companion.respond(question,thinker)
        companion.abort_turn()
        await companion.respond('nine am',thinker)
        self.assertEqual(await self.service.store.call('reminder_list'),[])
        reply=await companion.respond(question,thinker)
        companion.commit_spoken(question,reply)
        reply=await companion.respond('nine am',thinker)
        self.assertIn('09:00 BST',reply)
        self.assertEqual(len(await self.service.store.call('reminder_list')),1)

    async def test_conversation_has_fresh_authoritative_clock(self):
        companion=Companion(self.service.tools,timezone_name='Pacific/Auckland')
        thinker=Thinker()
        await companion.respond('Hello',thinker)
        self.assertIn('CURRENT LOCAL CLOCK',thinker.prompts[-1])
        self.assertIn('Pacific/Auckland',thinker.prompts[-1])


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_stop_restart_and_failed_start_release_old_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            FakeAppliance.live=FakeAppliance.maximum=0; FakeAppliance.fail=False
            controller=DesktopController(lambda n,d:None,directory=Path(tmp),appliance_factory=FakeAppliance)
            await controller.start()
            config={'port':'COM4','ssid':'Test lab','lan_host':'192.168.1.2'}
            try:
                await controller.command('server_start',config); await asyncio.sleep(0)
                with self.assertRaises(ValueError): await controller.command('server_start',config)
                with self.assertRaises(ValueError): await controller.command('timezone',{'timezone':'UTC'})
                await controller.command('server_restart',config); await asyncio.sleep(0)
                self.assertEqual(FakeAppliance.maximum,1)
                await controller.command('server_stop',{})
                self.assertEqual(FakeAppliance.live,0)
                await controller.command('reminder_create',{'text':'still useful','when':'in 20 minutes'})
                self.assertEqual(len((await controller.services.snapshot())['reminders']),1)
                FakeAppliance.fail=True
                await controller.command('server_start',config); await asyncio.sleep(0)
                self.assertIsNone(controller.app); self.assertEqual(controller.state,'stopped')
                self.assertEqual(FakeAppliance.live,0)
                FakeAppliance.fail=False
                await controller.command('server_start',config); await asyncio.sleep(0)
                self.assertEqual(FakeAppliance.live,1)
            finally: await controller.close()
            self.assertEqual(FakeAppliance.live,0)
