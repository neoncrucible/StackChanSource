"""Saved profiles, explicit tests and voice controls share the real camera authority."""
import asyncio
from dataclasses import asdict, replace
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from kcore.camera_manager import CameraConfig, CameraManager
from kcore.camera_voice import camera_plan
from kcore.companion import Companion
from kcore.desktop_worker import DesktopController
from kcore.perception_store import PerceptionStore
from kcore.schema import ensure_schema
from kcore.storage import KadencePaths
from test_autonomous_perception import controller, vector


def test_profile_edit_replacement_reopen_and_backup(tmp_path):
    async def case():
        worker=DesktopController(lambda *a:None,directory=tmp_path)
        await worker.start()
        store=PerceptionStore(worker.services.paths.database)
        person=store.call('enroll',name='Boss',vectors=[vector()]*3)
        await worker.command('face_update',{'person_id':person,'name':'Den','recognition_enabled':True,'greeting_enabled':False})
        with pytest.raises(ValueError):store.call('enroll',name='Den',person=person,vectors=[[0]*128]*3)
        assert len(store.call('profiles'))==3
        store.call('enroll',name='Den',person=person,vectors=[vector(1)]*3)
        data=await worker.command('face_profiles',{})
        assert data['persons'][0]['compatible_samples']==3
        assert data['persons'][0]['samples']==3
        assert data['persons'][0]['id']==person
        assert data['persons'][0]['greeting_enabled']==0
        assert 'embedding' not in json.dumps(data)
        backup=await worker.command('database_backup',{})
        with sqlite3.connect(backup['path']) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('SELECT display_name FROM persons').fetchone()[0]=='Den'
        await worker.close()
        reopened=DesktopController(lambda *a:None,directory=tmp_path);await reopened.start()
        rows=(await reopened.command('face_profiles',{}))['persons']
        assert rows[0]['id']==person and rows[0]['samples']==3
        await reopened.command('face_forget',{'person_id':person})
        assert not (await reopened.command('face_profiles',{}))['persons']
        assert not store.call('profiles')
        await reopened.close()
    asyncio.run(case())


def test_manual_recognition_is_two_frames_without_automatic_enable_or_greeting(tmp_path):
    async def case():
        e=await controller(tmp_path,enabled=False,policy='OFF',greetings=True)
        await e.pc.db('enroll',name='Boss',vectors=[vector()]*3)
        result=await e.pc.test_recognition()
        assert result['names']==['Boss'] and result['frames']==2
        assert e.camera.acquire.await_count==2 and not e.delivered
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT count(*) FROM perception_actions').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM presence_sessions').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM media').fetchone()[0]==0
        e.camera.configure(replace(e.camera.config,privacy=True))
        with pytest.raises(RuntimeError,match='privacy'):await e.pc.test_recognition()
        assert e.camera.acquire.await_count==2
        await e.pc.close()
    asyncio.run(case())


def test_ambiguous_manual_match_does_not_name_anyone(tmp_path):
    async def case():
        e=await controller(tmp_path,enabled=False)
        for name in ('One','Two'):await e.pc.db('enroll',name=name,vectors=[vector()]*3)
        result=await e.pc.test_recognition()
        assert result['names']==[] and 'No enrolled identity' in result['message']
        await e.pc.close()
    asyncio.run(case())


def test_enrollment_feedback_and_voice_interrupt_keep_old_samples(tmp_path):
    async def case():
        e=await controller(tmp_path,enabled=False)
        await e.pc.enroll('Boss')
        person=(await e.pc.db('persons'))[0]['id']
        assert [d['sample'] for n,d in e.events if n=='enrollment' and d['state']=='accepted']==[1,2,3]
        assert any(n=='enrollment' and d['state']=='saved' for n,d in e.events)
        entered=asyncio.Event()
        async def slow(**kwargs):entered.set();await asyncio.Event().wait()
        e.camera.acquire=AsyncMock(side_effect=slow)
        task=asyncio.create_task(e.pc.enroll('Boss',person))
        await entered.wait()
        await e.pc.interrupt()
        with pytest.raises(asyncio.CancelledError):await task
        assert len(await e.pc.db('profiles'))==3
        assert e.pc._explicit_task is None and not e.pc._enrolling
        await e.pc.close()
    asyncio.run(case())


class NoPlanner:
    async def stream_reply(self,prompt):
        raise AssertionError('Direct camera phrases must not wait for the reasoning provider')
        yield ''


class Proposal:
    async def stream_reply(self,prompt):
        yield json.dumps({'tool':'camera_control','arguments':{'command':'privacy_off'}})


def test_voice_commands_are_direct_but_model_changes_need_confirmation(tmp_path):
    async def case():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        companion=Companion(worker.services.tools)
        look=AsyncMock(return_value={'spoken':'A mug on the desk.'})
        worker.services.look_handler=look
        assert await companion.respond('What can you see?',NoPlanner())=='A mug on the desk.'
        look.assert_awaited_once_with('What can you see?')
        await companion.respond('Use the extra camera',NoPlanner())
        assert CameraConfig.load(tmp_path).source=='unitv2-camera'
        await companion.respond('Use the robot camera',NoPlanner())
        await companion.respond('Switch to extra camera',NoPlanner())
        assert CameraConfig.load(tmp_path).source=='unitv2-camera'
        reply=await companion.respond('Enable greetings',NoPlanner())
        assert 'still off' in reply
        await companion.respond('Turn privacy on',NoPlanner())
        assert CameraConfig.load(tmp_path).privacy
        assert 'UnitV2 extra camera' in await companion.respond('Camera status',NoPlanner())
        reply=await companion.respond('Tell me a joke',Proposal())
        assert 'Say yes' in reply and CameraConfig.load(tmp_path).privacy
        companion.commit_spoken('Tell me a joke',reply)
        await companion.respond('yes',NoPlanner())
        assert not CameraConfig.load(tmp_path).privacy
        await worker.close()
    asyncio.run(case())


@pytest.mark.parametrize('phrase',["don't turn privacy off",'if I say turn privacy off what happens','please explain automatic perception','the label says enable greetings'])
def test_indirect_or_negative_text_does_not_authorize_settings(phrase):
    assert camera_plan(phrase) is None


def test_voice_and_desktop_share_lifecycle_gate_and_partial_settings(tmp_path):
    async def case():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        result=await worker.camera_voice('perception_on')
        assert 'TEST START / STOP' in result['spoken']
        assert not CameraConfig.load(tmp_path).perception_enabled
        await worker.command('camera_settings',asdict(CameraConfig(source='robot-camera',address='192.168.40.175')))
        await worker.camera_voice('perception_on')
        saved=CameraConfig.load(tmp_path)
        assert saved.source=='robot-camera' and saved.policy=='EVENT_ONLY' and saved.perception_enabled
        await worker.camera_voice('privacy_on')
        assert CameraConfig.load(tmp_path).privacy
        await worker.close()
    asyncio.run(case())


def test_voice_look_uses_selected_source_and_privacy_without_second_serial_owner(tmp_path):
    from kcore.appliance import KadenceAppliance
    async def case():
        e=await controller(tmp_path,source='unitv2-camera',enabled=False)
        from kcore.vision import DeskVision
        vision=DeskVision();vision.guard=e.camera.check
        vision.describe=AsyncMock(return_value={'spoken':'A desk.'})
        capture=AsyncMock()
        app=SimpleNamespace(camera=e.camera,perception=e.pc,vision=vision,settings=SimpleNamespace(providers=SimpleNamespace(gemini_api_key='fake-test-only')),_capture_in_voice=capture,emit=lambda *a:None)
        assert (await KadenceAppliance._look_during_voice(app,'What can you see?'))['spoken']=='A desk.'
        assert e.camera.acquire.call_args.kwargs=={'purpose':'voice','in_voice':capture}
        assert vision.source_device=='unitv2-camera'
        capture.assert_not_called()
        e.camera.configure(replace(e.camera.config,privacy=True))
        with pytest.raises(RuntimeError,match='privacy'):await KadenceAppliance._look_during_voice(app,'look')
        assert e.camera.acquire.await_count==1
        await e.pc.close()
    asyncio.run(case())


def test_vision_tabs_and_saved_feedback_exclude_names_from_diagnostics(tmp_path):
    from PySide6.QtWidgets import QApplication
    from kcore.desktop_ui import MainWindow
    qt=QApplication.instance() or QApplication([])
    window=MainWindow(directory=tmp_path,load_credentials=False)
    try:
        assert [window.vision_tabs.tabText(i) for i in range(4)]==['Camera','Perception','Profiles','Activity']
        window.faces_result({'ok':True,'result':{'database':'test/database/kadence.sqlite3','persons':[{'id':'sample','display_name':'Private name','samples':3,'compatible_samples':3,'recognition_enabled':1,'greeting_enabled':1,'enrolled_at':1}]}})
        assert window.profiles_table.rowCount()==1 and window.profile_name.text()=='Private name'
        assert '3 compatible' in window.profile_summary.text()
        window.on_event('enrollment',{'state':'accepted','sample':2})
        assert window.enrollment_progress.value()==2
        window.on_event('enrollment',{'state':'failed','message':'Exactly one clear face required.'})
        assert 'Exactly one' in window.enrollment_result.text()
        window.on_event('vision_activity',{'kind':'recognition_test','message':'Recognised: Private name.'})
        assert 'Private name' in window.reflex_log.toPlainText()
        assert 'Private name' not in json.dumps(list(window.diagnostic))
        window.navigate(3);window.vision_tabs.setCurrentIndex(1);window.show();qt.processEvents()
        assert window.perception_enable.isVisible()
    finally:window.ticker.stop();window.quitting=True;window.close()


def test_worker_event_test_uses_real_gates_and_preserves_visit_on_identical_save(tmp_path):
    from kcore.vision import DeskVision
    async def case():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        e=await controller(tmp_path,greetings=True)
        worker.app=SimpleNamespace(camera=e.camera,perception=e.pc,vision=DeskVision())
        try:
            await e.pc.db('enroll',name='Boss',vectors=[vector()]*3)
            result=await worker.command('perception_test',{})
            assert 'Recognised: Boss.' in result['message'] and 'Greeting: delivered' in result['message']
            assert len(e.delivered)==1 and e.camera.acquire.await_count==2
            run=e.pc.run; generation=e.camera.generation
            await worker.command('camera_settings',asdict(e.camera.config))
            assert e.pc.run==run and e.camera.generation==generation and e.pc._visit_greeted
            with pytest.raises(RuntimeError,match='cooldown'):await worker.command('perception_test',{})
            e.now[0]=25
            result=await worker.command('perception_test',{})
            assert 'already attempted' in result['message'] and len(e.delivered)==1
            e.camera.configure(replace(e.camera.config,privacy=True))
            with pytest.raises(RuntimeError,match='Privacy'):await worker.command('perception_test',{})
            assert e.camera.acquire.await_count==4
        finally:
            await e.pc.close();worker.app=None;await worker.close()
    asyncio.run(case())
