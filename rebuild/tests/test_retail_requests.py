"""Everyday camera language and shared desktop/voice behaviour."""
import asyncio
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from kcore.camera_manager import CameraConfig
from kcore.camera_voice import camera_plan
from kcore.companion import Companion
from kcore.desktop_worker import DesktopController


@pytest.mark.parametrize('text', [
    'What can you see?', 'What are you looking at?', "What's in front of you?",
    'What colour is this?', 'What color is the pen?', 'What shape is that?',
    'Hey Kadence, could you please tell me what colour this is?',
    'Kade, please describe what you see.', 'Would you read this for me please?',
    'Please take a look at the desk.', 'Can you identify this?',
    'Tell me the colour of this mug.', 'Can you see what I am holding?',
    'What am I holding?', 'Read the label.', 'Scan the QR code.',
    'What can you see, with description?',
])
def test_visual_requests_are_local_and_keep_the_original_question(text):
    assert camera_plan(text) == {'tool':'desk_look','arguments':{'question':text}}


@pytest.mark.parametrize('text', [
    'Read my list', 'Read my notes', 'Describe the French Revolution',
    'What colour is Mars?', 'How can I track a parcel?',
    "Don't track the pen", 'Do not turn privacy off',
    'If I say stop tracking what happens?', 'The label says turn privacy off',
    'Explain what can you see means', 'I can see a red mug',
])
def test_unrelated_negative_and_quoted_requests_do_not_use_the_camera(text):
    assert camera_plan(text) is None


@pytest.mark.parametrize('text,target', [
    ('Track the pen','the pen'), ('Please follow this mug','this mug'),
    ('Hey Kadence, could you track the pen for me please?','the pen'),
    ('Keep track of the red ball','the red ball'),
    ('Can you keep an eye on this object?','this object'),
    ('Track snow','snow'),
])
def test_natural_tracking_requests_preserve_the_target(text,target):
    assert camera_plan(text)=={'tool':'tracking_control','arguments':{'action':'follow','target':target}}


def test_voice_colour_and_factory_commands_do_not_wait_for_model_or_confirmation(tmp_path):
    class Offline:
        async def stream_reply(self, text):
            raise AssertionError('An explicit camera request must use the local intent path')
            yield ''
    async def run():
        worker=DesktopController(lambda *args:None,directory=tmp_path)
        await worker.start()
        try:
            worker.services.look_handler=AsyncMock(return_value={'spoken':'The mug is red.'})
            worker.services.factory_handler=AsyncMock(return_value={'spoken':'Shape detection is running.'})
            companion=Companion(worker.services.tools)
            assert await companion.respond('Could you tell me what colour the mug is?',Offline())=='The mug is red.'
            assert await companion.respond('Please start shape recognition',Offline())=='Shape detection is running.'
            worker.services.factory_handler.assert_awaited_once_with({'action':'start','mode':'shape_detector'})
        finally:
            await worker.close()
    asyncio.run(run())


def test_home_requests_use_the_existing_operations_without_rewriting_settings(tmp_path):
    async def run():
        worker=DesktopController(lambda *args:None,directory=tmp_path)
        await worker.start()
        try:
            saved=CameraConfig(privacy=False,policy='OFF',source='auto')
            saved.save(tmp_path)
            camera=SimpleNamespace(config=saved)
            tracker=SimpleNamespace(stop=AsyncMock(),busy=lambda:False,
                select=AsyncMock(return_value={'spoken':'I am tracking the pen.'}))
            worker.app=SimpleNamespace(camera=camera,tracking=tracker,factory=SimpleNamespace(stop=AsyncMock()),
                look_camera=AsyncMock(return_value={'spoken':'A red mug.'}))
            assert (await worker.command('camera_request',{'text':'What colour is this?'}))['spoken']=='A red mug.'
            worker.app.look_camera.assert_awaited_once_with('What colour is this?')
            assert (await worker.command('camera_request',{'text':'Could you track the pen?'}))['spoken']=='I am tracking the pen.'
            tracker.select.assert_awaited_once_with(target='the pen')
            assert CameraConfig.load(tmp_path)==saved
            with pytest.raises(ValueError):
                await worker.command('camera_request',{'text':'Tell me a joke'})
        finally:
            worker.app=None
            await worker.close()
    asyncio.run(run())
