"""Owner language reaches real capabilities, including multi-turn corrections."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from kcore.camera_voice import camera_plan
from kcore.companion import Companion
from kcore.reminder_time import resolve_when, split_reminder_request
from kcore.reminders import Reminders
from kcore.services import LocalServices
from kcore.utility_store import UtilityStore


class Offline:
    async def stream_reply(self, text):
        raise AssertionError('Familiar wording should not wait for a model')
        yield ''


class Planner:
    def __init__(self, plan): self.plan, self.prompts = plan, []
    async def stream_reply(self, text):
        self.prompts.append(text)
        yield json.dumps(self.plan)


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('phrase', [
    "What's this?", 'What is this?', 'What am I holding?', 'Can you see this?',
    "What's in my hand?", 'Identify this', 'What do I have in my hand?',
    "What have I got in my hand?", "What's this I'm holding?", "What's that I'm holding?",
    'What object am I holding?', 'Which thing is this?', 'Tell me what I am holding',
    'Please tell me what is in my hand', 'Could you identify this for me?',
    'Hey Kade, would you describe this?', 'What colour is this?', 'What color is that?',
    'What colour is the bottle?', 'What colour does the bottle look?',
    'Can you see the bottle?', 'Is it still there?', 'Is the bottle blue?',
    'Where is the bottle?', 'Read this', 'Read the label', 'Scan this',
    'Have a look at this', 'Take a look at my hand', 'What can you see?',
    "What's on my desk?", 'What are you looking at?', 'Let me know what this is',
])
def test_current_view_language_keeps_the_exact_question(phrase):
    assert camera_plan(phrase) == {'tool':'desk_look', 'arguments':{'question':phrase}}


CREATE_PHRASES = [
    'Remind me to check the print in twenty minutes',
    'Could you remind me to check the print in twenty minutes?',
    'Hey Kade, please remind me to check the print in twenty minutes',
    'Would you mind reminding me to check the print in twenty minutes?',
    'Set a reminder to check the print in twenty minutes',
    'Set me a reminder to check the print in twenty minutes',
    'Set up a reminder to check the print in twenty minutes',
    'Create a reminder for me to check the print in twenty minutes',
    'Add a reminder to check the print in twenty minutes',
    'Schedule a reminder to check the print in twenty minutes',
    "I'd like a reminder to check the print in twenty minutes",
    'I need a reminder to check the print in twenty minutes',
    "Don't let me forget to check the print in twenty minutes",
    'Do not let me forget to check the print in twenty minutes',
    "Make sure I don't forget to check the print in twenty minutes",
    'Nudge me in twenty minutes to check the print',
    'Ping me in twenty minutes to check the print',
    'Alert me in twenty minutes to check the print',
    'Notify me in twenty minutes to check the print',
    'Let me know in twenty minutes that I need to check the print',
    'In twenty minutes remind me to check the print',
    'Remind me in twenty minutes to check the print',
    'Set a reminder for in twenty minutes to check the print',
    'Can you please set a reminder to check the print in twenty minutes for me?',
]


@pytest.mark.parametrize('phrase', CREATE_PHRASES)
def test_reminder_wording_preserves_task_and_time(phrase):
    task, when = split_reminder_request(phrase)
    assert task in {'check the print', 'I need to check the print'}
    assert resolve_when(when, now=NOW, timezone_name='Europe/London').due == NOW+timedelta(minutes=20)


@pytest.mark.parametrize('phrase', [
    "Don't remind me to check the print", 'Do not set a reminder for 7 pm',
    'How do I set a reminder?', 'Explain what remind me means',
    'If I say remind me tomorrow, what happens?', 'Tell me a story about a reminder',
    'I reminded myself to buy milk', 'What are reminders?',
    'Let me know what you think of that idea', 'That reminds me of yesterday',
    'Remind me what we were talking about', 'Remind me where I saved that note',
])
def test_mentions_and_negations_are_not_creation_requests(phrase):
    assert split_reminder_request(phrase) is None


@pytest.mark.parametrize('when,seconds', [
    ('in half an hour',1800), ('in a quarter of an hour',900),
    ('in an hour and a half',5400), ('in two and a half hours',9000),
    ('in one hour and twenty minutes',4800), ('twenty minutes from now',1200),
    ('after ten minutes',600), ('in a week',604800), ('ten-minute',600),
])
def test_natural_durations(when,seconds):
    assert resolve_when(when,now=NOW,timezone_name='Europe/London').due == NOW+timedelta(seconds=seconds)


def test_local_reminder_journey_creation_correction_named_cancel_and_snooze(tmp_path):
    async def run():
        service=LocalServices(tmp_path); await service.start()
        service.reminders.now=lambda:NOW
        companion=Companion(service.tools,reminders=service.reminders)
        try:
            for phrase in CREATE_PHRASES:
                reply=await companion.respond(phrase,Offline())
                assert ' set for ' in reply
                companion.commit_spoken(phrase,reply)
            rows=await service.store.call('reminder_list')
            assert len(rows)==len(CREATE_PHRASES)
            assert {row['due'] for row in rows} == {(NOW+timedelta(minutes=20)).timestamp()}
            reply=await companion.respond('Actually, make that 7 pm instead',Offline())
            assert '19:00 BST' in reply and ' moved to ' in reply
            assert len(await service.store.call('reminder_list')) == len(rows)
            assert 'Snoozed' in await companion.respond('Snooze that for ten minutes',Offline())
            assert 'cancelled' in await companion.respond('Cancel that reminder',Offline())
            reply=await companion.respond('Set a reminder to order filament tomorrow at noon',Offline())
            assert ' set for ' in reply
            assert 'cancelled' in await companion.respond('Delete the filament reminder',Offline())
        finally: await service.close()
    asyncio.run(run())


def test_clarification_keeps_day_task_and_single_record(tmp_path):
    async def run():
        service=LocalServices(tmp_path); await service.start(); service.reminders.now=lambda:NOW
        c=Companion(service.tools,reminders=service.reminders)
        async def say(text):
            reply=await c.respond(text,Offline()); c.commit_spoken(text,reply); return reply
        try:
            assert 'What time' in await say("Don't let me forget to order filament tomorrow")
            assert 'am or pm' in await say('Make it nine instead')
            assert 'Friday 16 October 2026, 09:00 BST' in await say('In the morning please')
            assert len(await service.store.call('reminder_list'))==1
            assert 'What should' in await say('Set a reminder for 7 pm')
            assert '19:00 BST' in await say('To check the print')
            assert len(await service.store.call('reminder_list'))==2
            assert ' moved to ' in await say('Move the print reminder to tomorrow at 8 pm')
            assert len(await service.store.call('reminder_list'))==2
        finally:await service.close()
    asyncio.run(run())


def test_conditions_use_real_watch_or_explain_missing_capability(tmp_path):
    async def run():
        service=LocalServices(tmp_path); await service.start(); service.reminders.now=lambda:NOW
        service.tracking_handler=AsyncMock(return_value={'spoken':'Watching the blue bottle for movement or loss of sight.'})
        c=Companion(service.tools,reminders=service.reminders)
        try:
            reply=await c.respond('Remind me when the blue bottle moves',Offline())
            assert reply.startswith('Watching')
            service.tracking_handler.assert_awaited_once_with({'action':'watch','target':'the blue bottle'})
            for wording in ('Remind me if someone moves the bottle','Let me know when I hide the bottle','Warn me if anybody takes the bottle'):
                assert 'Watching' in await c.respond(wording,Offline())
                service.tracking_handler.assert_awaited_with({'action':'watch','target':'the bottle'})
            reply=await c.respond('Remind me when I get home to order filament',Offline())
            assert "can't detect that condition" in reply
            assert await service.store.call('reminder_list') == []
            c.commit_spoken('Remind me when I get home to order filament',reply)
            assert ' set for ' in await c.respond('Tomorrow at noon',Offline())
            reply=await c.respond('Remind me to order filament every Monday at 9 am',Offline())
            assert 'Repeating reminders' in reply
            assert len(await service.store.call('reminder_list')) == 1
        finally:await service.close()
    asyncio.run(run())


@pytest.mark.parametrize('text,tool,args', [
    ("Any idea what I've got here?",'desk_look',{'question':'What is this?'}),
    ('Could you inspect this for me?', 'desk_look', {'question':'Inspect this'}),
    ("I'd like you to keep that bottle centred as I move it", 'tracking_control', {'action':'follow','target':'that bottle'}),
    ('Give me a prod in twenty minutes to check the print', 'reminder_create', {'text':'check the print','when':'in twenty minutes'}),
    ('Send me a nudge tomorrow at noon to order filament', 'reminder_create', {'text':'order filament','when':'tomorrow at noon'}),
    ('Push back the filament reminder to tomorrow at noon', 'reminder_manage', {'action':'reschedule','target':'filament','when':'tomorrow at noon'}),
])
def test_unfamiliar_wording_uses_semantic_tools_without_redundant_confirmation(tmp_path,text,tool,args):
    async def run():
        service=LocalServices(tmp_path);await service.start();service.reminders.now=lambda:NOW
        service.look_handler=AsyncMock(return_value={'spoken':'A blue bottle, Boss.'})
        service.tracking_handler=AsyncMock(return_value={'spoken':'The bottle is locked; following begins after speech.'})
        c=Companion(service.tools,reminders=service.reminders);model=Planner({'tool':tool,'arguments':args})
        try:
            if tool=='reminder_manage':await service.reminders.create('order filament','in 10 minutes')
            reply=await c.respond(text,model)
            assert model.prompts and 'Say yes' not in reply
            if tool=='desk_look': service.look_handler.assert_awaited_once_with(text)
            if tool=='tracking_control': service.tracking_handler.assert_awaited_once_with(args)
            if tool.startswith('reminder_'): assert len(await service.store.call('reminder_list'))==1
        finally:await service.close()
    asyncio.run(run())


def test_semantic_clarification_rejects_invented_times_and_false_success(tmp_path):
    async def run():
        service=LocalServices(tmp_path);await service.start();service.reminders.now=lambda:NOW
        c=Companion(service.tools,reminders=service.reminders)
        try:
            reply=await c.respond('Give me a nudge to order filament',Planner({'tool':'reminder_create','arguments':{'text':'order filament','when':'tomorrow at 7 pm'}}))
            assert 'What date and time' in reply
            assert await service.store.call('reminder_list')==[]
            c.commit_spoken('Give me a nudge to order filament',reply)
            assert ' set for ' in await c.respond('Tomorrow at noon',Offline())
            reply=await c.respond('Send me a nudge sometime',Planner({'reply':"I've set a reminder for tomorrow."}))
            assert "haven't changed your reminders" in reply
            assert len(await service.store.call('reminder_list'))==1
        finally:await service.close()
    asyncio.run(run())


def test_ambiguous_names_and_new_topics_do_not_change_reminders(tmp_path):
    async def run():
        store=UtilityStore(tmp_path);await store.start();r=Reminders(store,now=lambda:NOW)
        try:
            await r.create('check print quality','in 10 minutes');await r.create('check print completion','in 20 minutes')
            reply,_=await r.voice_request('Cancel the print reminder')
            assert 'Which reminder' in reply and len(await store.call('reminder_list'))==2
            _,draft=await r.voice_request('Remind me to order filament tomorrow')
            assert await r.voice_request('What is in my hand?',draft) is None
            r._recent_at=0
            assert await r.voice_request('Actually, make it noon') is None
        finally:await store.close()
    asyncio.run(run())
