"""Real SQLite/files and explicit camera paths; photos never enter automatic work."""
import asyncio
import base64
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest
from PIL import Image

from kcore.face_media import ProfilePhotos, reference
from kcore.local_faces import LocalFaces, quality_message
from kcore.perception_store import PerceptionStore
from kcore.schema import ensure_schema
from kcore.storage import KadencePaths
from test_autonomous_perception import controller, vector
from test_live_faces import fast_face_clock, install_training


def photo():
    output=io.BytesIO();Image.new('RGB',(160,120),'#49776c').save(output,format='PNG')
    return {'png':output.getvalue(),'source':'unitv2-camera','captured':1700000000.0}


def test_review_photos_survive_restart_and_failed_replace_is_atomic(tmp_path):
    paths=KadencePaths.for_root(tmp_path);ensure_schema(paths)
    store=PerceptionStore(paths.database)
    person=store.call('enroll',name='Test profile',vectors=[vector()]*3,references=[photo()]*3)
    saved=list((tmp_path/'media'/'face-profiles').glob('*.png'))
    assert len(saved)==3
    reopened=PerceptionStore(paths.database)
    assert reopened.call('persons')[0]['photo_count']==3
    assert [base64.b64decode(p['png_base64']) for p in reopened.call('photos',person=person)]==[photo()['png']]*3
    # Fail after the new files are written and old rows deleted, inside SQL.
    with sqlite3.connect(paths.database) as db:
        db.execute("CREATE TRIGGER reject_samples BEFORE INSERT ON face_profiles BEGIN SELECT RAISE(ABORT,'fixture storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        reopened.call('enroll',name='Test profile',person=person,vectors=[vector(1)]*3,references=[photo()]*3)
    assert set(saved)==set((tmp_path/'media'/'face-profiles').glob('*.png'))
    assert all(v==vector() for _,v in reopened.call('profiles'))
    with sqlite3.connect(paths.database) as db:
        assert db.execute('SELECT count(*) FROM media').fetchone()[0]==3
        db.execute('DROP TRIGGER reject_samples')
    # Replacing with embedding-only samples removes the superseded photos.
    reopened.call('enroll',name='Test profile',person=person,vectors=[vector(1)]*3)
    assert reopened.call('persons')[0]['photo_count']==0
    assert not any(p.exists() for p in saved)
    reopened.call('enroll',name='Test profile',person=person,vectors=[vector(1)]*3,references=[photo()]*3)
    reopened.call('forget',person=person)
    assert not reopened.call('persons') and not reopened.call('photos',person=person)
    assert not list((tmp_path/'media'/'face-profiles').glob('*.png'))
    with sqlite3.connect(paths.database) as db:
        assert db.execute('SELECT count(*) FROM media').fetchone()[0]==0
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_failed_photo_delete_is_reported_and_retried(tmp_path):
    paths=KadencePaths.for_root(tmp_path);ensure_schema(paths);store=PerceptionStore(paths.database)
    person=store.call('enroll',name='Test profile',vectors=[vector()]*3,references=[photo()]*3)
    with patch.object(Path,'unlink',side_effect=PermissionError('locked')):
        with pytest.raises(RuntimeError,match='could not be deleted'):store.call('forget',person=person)
    assert len(list((tmp_path/'media'/'face-profiles').glob('*.png')))==3
    assert not store.call('persons')
    assert not list((tmp_path/'media'/'face-profiles').glob('*.png'))


def test_photo_reader_and_deletion_reject_unowned_paths(tmp_path):
    paths=KadencePaths.for_root(tmp_path);ensure_schema(paths);store=PerceptionStore(paths.database)
    person=store.call('enroll',name='Test profile',vectors=[vector()]*3,references=[photo()]*3)
    foreign=tmp_path/'foreign.png';foreign.write_bytes(photo()['png'])
    with sqlite3.connect(paths.database) as db:db.execute("UPDATE media SET path='foreign.png' WHERE id=(SELECT min(id) FROM media)")
    photos=store.call('photos',person=person)
    assert sum(p.get('unavailable',False) for p in photos)==1
    with pytest.raises(RuntimeError,match='could not be deleted'):store.call('forget',person=person)
    assert foreign.read_bytes()==photo()['png']
    for value in ('../outside.png','media/face-profiles/../../outside.png','C:/private.png'):
        with pytest.raises(ValueError):ProfilePhotos(paths.database).path(value)


def test_explicit_enrollment_preview_and_opt_in_photos_use_same_camera_frames(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,enabled=False,source='unitv2-camera')
        capture=e.camera.acquire.side_effect
        async def real_frame(**kwargs):return replace(await capture(**kwargs),png=photo()['png'],width=160,height=120)
        e.camera.acquire.side_effect=real_frame
        install_training(e)
        result=await e.pc.enroll('Test profile',keep_photos=True)
        assert '3 local review photos saved' in result['message']
        person=result['person_id'];saved=await e.pc.db('photos',person=person)
        assert len(saved)==3 and all(p['source']=='unitv2-camera' for p in saved)
        assert all(Image.open(io.BytesIO(base64.b64decode(p['png_base64']))).width<=256 for p in saved)
        previews=[d for n,d in e.events if n=='face_preview' and d.get('png_base64')]
        assert len(previews)==20
        result=await e.pc.test_recognition()
        assert result['names']==['Test profile']
        assert result['quality'][0]['usable']==1
        assert len(await e.pc.db('photos',person=person))==3
        e.camera.configure(replace(e.camera.config,privacy=True))
        await e.pc.reset('privacy')
        assert [d for n,d in e.events if n=='face_preview'][-1]=={}
        with pytest.raises(RuntimeError,match='privacy'):await e.pc.enroll('Blocked',keep_photos=True)
        assert e.camera.acquire.await_count==22
        await e.pc.close()
    asyncio.run(case())


def test_quality_report_distinguishes_no_detection_small_and_blurred(tmp_path):
    import numpy as np
    from types import SimpleNamespace
    faces=LocalFaces(tmp_path)
    rows=np.array([[0,0,20,20,*([0]*10),.99],[0,0,80,80,*([0]*10),.99],[0,0,90,90,*([0]*10),.99]],dtype=np.float32)
    faces._detector=SimpleNamespace(setInputSize=lambda _:None,detect=lambda _:(None,rows))
    gradient=np.repeat(np.tile(np.arange(112,dtype=np.uint8),(112,1))[:,:,None],3,axis=2)
    faces._recognizer=SimpleNamespace(alignCrop=lambda *_:gradient,feature=lambda _:np.array(vector()))
    with patch('cv2.Laplacian',side_effect=[SimpleNamespace(var=lambda:2),SimpleNamespace(var=lambda:50)]):
        usable,report=faces.analyze_details(photo()['png'])
    assert len(usable)==1 and report['detected']==3 and report['small']==1 and report['blurred']==1
    assert 'light' not in quality_message(report)
    assert '40 pixels' in quality_message({'detected':1,'usable':0,'small':1})
    assert 'blurred' in quality_message({'detected':1,'usable':0,'blurred':1})
    assert 'No face detected' in quality_message({'detected':0,'usable':0})


def test_match_failure_reports_score_without_blame_for_lighting(tmp_path):
    async def case():
        e=await controller(tmp_path,enabled=False)
        await e.pc.db('enroll',name='Other profile',vectors=[vector(1)]*3)
        result=await e.pc.test_recognition()
        assert 'Best similarity 0.000; required 0.55' in result['message']
        assert 'Usable faces by frame: 1 / 1' in result['message']
        assert 'light' not in result['message'] and not result['names']
        await e.pc.close()
    asyncio.run(case())


def test_gallery_and_temporary_preview_are_not_in_diagnostics(tmp_path):
    from PySide6.QtWidgets import QApplication
    from kcore.desktop_ui import MainWindow
    qt=QApplication.instance() or QApplication([])
    window=MainWindow(directory=tmp_path,load_credentials=False)
    window.control.send=lambda *a,**k:None
    try:
        window.faces_result({'ok':True,'result':{'persons':[{'id':'test','display_name':'Private profile','samples':3,'compatible_samples':3,'photo_count':3}]}})
        item={'png_base64':base64.b64encode(photo()['png']).decode(),'source':'unitv2-camera','captured':1700000000.0}
        window.show_profile_photos('test',{'ok':True,'result':{'photos':[item]*3}})
        assert '3 saved local' in window.photo_status.text()
        assert all(not p.pixmap().isNull() for p in window.profile_photo_labels)
        window.on_event('face_preview',{**item,'captured_at':item['captured'],'message':'One face'})
        assert not window.face_check_preview.pixmap().isNull()
        assert item['png_base64'] not in json.dumps(list(window.diagnostic))
        assert 'Private profile' not in json.dumps(list(window.diagnostic))
        window.on_event('face_preview',{})
        assert window.face_check_preview.pixmap().isNull()
        window.show_profile_photos('old selection',{'ok':True,'result':{'photos':[]}})
        assert '3 saved local' in window.photo_status.text()
    finally:window.ticker.stop();window.quitting=True;window.close()
