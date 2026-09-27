"""Native executable protocol over real subprocesses, HTTP and host ownership."""
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import threading
import uuid

import pytest
from PIL import Image

from kcore.camera_manager import CameraConfig, CameraManager
from kcore.native_faces import NativeSequence, NativeFace, read_faces
from kcore.perception import PerceptionController
from kcore.perception_store import PerceptionStore
from kcore.schema import ensure_schema
from kcore.storage import KadencePaths, connect_database
from kcore.unitv2_lifecycle import Client, UnitV2Owner, LifecycleError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'unitv2'))
import kadence_unitv2 as bridge
import kadence_native as native
KEY='ac'*32
DEVICE='12'*16
NAME='Fixture Person'


def seed(root,names=(NAME,)):
    (root/'data').mkdir(exist_ok=True)
    (root/'data'/native.INFO).write_text(json.dumps({'faces':[{'name':n} for n in names]}))
    (root/'data'/native.FEATURES).write_bytes(struct.pack('<128f',1,*([0]*127))*len(names))


@pytest.fixture
def native_service(tmp_path):
    seed(tmp_path)
    (tmp_path/'scene').write_text('recognized')
    output=io.BytesIO();Image.new('RGB',(320,240),'green').save(output,'JPEG')
    script=tmp_path/'native_fixture.py'
    script.write_text('JPEG='+repr(base64.b64encode(output.getvalue()).decode())+'\n'+r'''
import json,sys,time,threading,queue,struct
from pathlib import Path
commands=queue.Queue()
def input_loop():
 for line in sys.stdin:
  if not line.startswith('_'): commands.put(json.loads(line))
threading.Thread(target=input_loop,daemon=True).start()
names=[p['name'] for p in json.loads(Path('data/face_recognition_info.json').read_text())['faces']]
training=False;index=0;cleared=False
while True:
 while not commands.empty():
  cmd=commands.get();op=cmd['operation']
  if op=='train':
   index=cmd['face_id']
   if index==len(names): names.append(cmd['name'])
   else:names[index]=cmd['name']
   training=True;msg='Training '+names[index]
  elif op=='stoptrain':training=False;msg='Exit training mode.'
  elif op=='saverun':training=False;msg='Faces saved.'
  print(json.dumps({'running':'Face Recognition','msg':msg}),flush=True)
  if op=='saverun':
   time.sleep(.15)
   Path('data/face_recognition_features.dat').write_bytes(struct.pack('<128f',1,*([0]*127))*len(names))
   Path('data/face_recognition_info.json').write_text(json.dumps({'faces':[{'name':n} for n in names]}))
 scene=Path('scene').read_text()
 if scene=='silent':time.sleep(.03);continue
 face={'x':160,'y':80,'w':200,'h':280,'prob':.99,'name':names[index] if training else names[0],'match_prob':.94}
 if training: print(json.dumps(dict(running='Face Recognition',status='training',**face)),flush=True)
 elif scene=='empty':
  if not cleared:print('{"render":0}',flush=True);cleared=True
 else:
  cleared=False;faces=[face]
  if scene=='duplicate':faces.append(dict(face,x=390,w=150))
  print(json.dumps({'running':'Face Recognition','num':len(faces),'face':faces}),flush=True)
 print(json.dumps({'img':JPEG}),flush=True)
 time.sleep(.04)
''')
    producer=bridge.Producer([sys.executable,str(script)],str(tmp_path))
    manager=native.NativeBridge(producer,bridge.CameraError,tmp_path,DEVICE,command=[sys.executable,str(script)])
    server=bridge.Server(('127.0.0.1',0),bridge.CameraService(producer,KEY))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    watcher=threading.Thread(target=producer.watchdog,daemon=True);watcher.start()
    client=Client('127.0.0.1',KEY,port=server.server_port)
    yield producer,manager,client,tmp_path
    producer.close();server.shutdown();server.server_close();thread.join(2);watcher.join(2)


def web(client,path,doc=None,cookie=None,origin=True):
    connection=http.client.HTTPConnection(client.address,client.port,timeout=10)
    headers={}
    if cookie:headers['Cookie']='kadence_native='+cookie
    if origin:headers['Origin']=f'http://{client.address}:{client.port}'
    if doc is not None:headers['Content-Type']='application/json'
    connection.request('POST' if doc is not None else 'GET',path,json.dumps(doc) if doc is not None else None,headers)
    response=connection.getresponse();body=response.read();status=response.status
    cookie_value=response.getheader('Set-Cookie')
    connection.close()
    return status,body,cookie_value


def open_web(client):
    lease=uuid.uuid4().hex
    ticket=client.call('web_open',lease)['ticket']
    status,_,cookie=web(client,'/native/session',{'ticket':ticket})
    assert status==200
    return lease,cookie.split(';')[0].split('=')[1]


def test_native_catalog_and_fresh_recognition_without_pc_embeddings(native_service):
    producer,manager,client,root=native_service
    value=client.call('face_profiles')
    assert value['profiles']==[{'native_id':0,'name':NAME}] and 'embedding' not in json.dumps(value)
    lease=uuid.uuid4().hex;client.call('face_start',lease)
    first=client.call('face_frame',lease);second=client.call('face_frame',lease)
    assert second['result_sequence']>first['result_sequence']
    assert read_faces(second['result'])[0].score==.94
    assert first['device_id']==DEVICE and first['revision']==value['revision']
    assert client.call('stop',lease)['stop_confirmed'] and producer.process is None


def test_disappearance_clears_identity_even_when_factory_omits_num_zero(native_service):
    _,_,client,root=native_service
    lease=uuid.uuid4().hex;client.call('face_start',lease)
    assert client.call('face_frame',lease)['result']['num']==1
    (root/'scene').write_text('empty')
    for _ in range(2): assert client.call('face_frame',lease)['result']=={'num':0,'face':[]}


def test_web_training_uses_original_commands_and_verifies_actual_saved_files(native_service):
    producer,manager,client,root=native_service
    lease,cookie=open_web(client)
    status,body,_=web(client,'/data_from_device',{},cookie)
    assert status==200 and json.loads(body)['faces']==[{'name':NAME}]
    status,_,_=web(client,'/data_to_device',{'operation':'train','face_id':1,'name':'Second Profile'},cookie)
    assert status==200
    with producer.changed:
        assert producer.changed.wait_for(lambda:manager.accepted>0,timeout=2)
    status,body,_=web(client,'/data_to_device',{'operation':'saverun'},cookie)
    assert status==200 and 'saved and verified' in json.loads(body)['message']
    assert [p['name'] for p in native.catalog(root)['profiles']]==[NAME,'Second Profile']
    assert list((root/'kadence-native-backups').glob('*/'+native.FEATURES))
    assert web(client,'/native/finish',{},cookie)[0]==200
    assert producer.status()['stop_confirmed']
    assert web(client,'/data_to_device',{'operation':'train','face_id':0,'name':NAME},cookie)[0]==401


def test_browser_cannot_renew_host_permission_or_restart_after_privacy_stop(native_service):
    producer,manager,client,_=native_service
    lease,cookie=open_web(client)
    expires=producer.expires
    assert web(client,'/native/state',{},cookie)[0]==200
    assert web(client,'/native/frame',cookie=cookie)[0] in {200,503}
    assert producer.expires==expires
    client.call('stop')
    assert web(client,'/native/state',{},cookie)[0]==401
    assert producer.starts==1 and producer.status()['stop_confirmed']


def test_web_requires_pairing_ticket_cookie_and_same_origin(native_service):
    producer,manager,client,_=native_service
    assert web(client,'/data_to_device',{'operation':'train','face_id':0,'name':NAME})[0]==401
    lease,cookie=open_web(client)
    assert web(client,'/native/state',{},cookie,origin=False)[0]==403
    assert web(client,'/native/session',{'ticket':'0'*32})[0]==401
    assert web(client,'/data_to_device',{'operation':'reset'},cookie)[0]==400
    assert not manager.dirty


def test_browser_disconnect_expires_owned_native_process(native_service):
    producer,manager,client,_=native_service
    _,cookie=open_web(client)
    child=producer.process
    manager.browser_seen-=31
    producer.watchdog_once()
    assert child.poll() is not None and producer.status()['stop_confirmed']


def test_invalid_native_file_pair_is_preserved_and_never_loaded(native_service):
    producer,_,client,root=native_service
    path=root/'data'/native.FEATURES;path.write_bytes(b'incomplete')
    with pytest.raises(LifecycleError):client.call('face_profiles')
    with pytest.raises(LifecycleError):client.call('face_start',uuid.uuid4().hex)
    assert path.read_bytes()==b'incomplete' and producer.starts==0


def test_duplicate_or_changed_identities_never_inherit_confirmation():
    a=NativeFace((.2,.2,.2,.4),'A',.94,.99)
    b=NativeFace((.2,.2,.2,.4),'B',.95,.99)
    sequence=NativeSequence({'A':'person-a','B':'person-b'})
    sequence.update([a]);sequence.update([a]);assert sequence.confirmed=={'person-a'}
    sequence.update([b]);assert not sequence.confirmed
    sequence.update([a,a]);assert not sequence.confirmed
    sequence.update([]);assert not sequence.confirmed


def test_schema_upgrade_and_native_sync_keep_greeting_preferences_without_face_vectors(tmp_path):
    paths=KadencePaths.for_root(tmp_path/'host');ensure_schema(paths,target=4)
    ensure_schema(paths)
    store=PerceptionStore(paths.database)
    catalog={'device_id':DEVICE,'revision':'a'*64,'profiles':[{'native_id':0,'name':NAME}]}
    person=store.call('sync_native',catalog=catalog)[NAME]
    store.call('update_person',person=person,name='Greeting Name',recognition_enabled=True,greeting_enabled=False)
    assert store.call('sync_native',catalog=catalog)[NAME]==person
    row=store.call('persons')[0]
    assert row['display_name']=='Greeting Name' and not row['greeting_enabled'] and row['provider']=='unitv2-native'
    with connect_database(paths.database) as db:
        assert db.execute('SELECT count(*) FROM face_profiles').fetchone()[0]==0
        assert db.execute('PRAGMA user_version').fetchone()[0]==5
    empty=dict(catalog,profiles=[],revision='b'*64)
    assert store.call('sync_native',catalog=empty)=={}
    assert store.call('persons')[0]['native_available']==0
    assert store.call('sync_native',catalog=catalog)[NAME]==person


def test_native_matches_drive_greeting_after_producer_release_without_loading_pc_model(native_service,tmp_path):
    producer,_,client,_=native_service
    async def run():
        paths=KadencePaths.for_root(tmp_path/'host');ensure_schema(paths)
        camera=CameraManager(None,config=CameraConfig(source='unitv2-camera',address='127.0.0.1',policy='EVENT_ONLY',perception_enabled=True,greetings=True))
        camera.unitv2=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=client.port))
        await camera.unitv2._select('127.0.0.1');camera.unitv2.verified=True
        delivered=[]
        async def deliver(action,check):
            check();assert producer.status()['stop_confirmed'];delivered.append(action)
        pc=PerceptionController(camera,paths,lambda *a:None,deliver,lambda:False)
        pc.faces.analyze_details=lambda *a:(_ for _ in ()).throw(AssertionError('PC face matcher must not run'))
        await pc.start()
        await pc._burst('gesture')
        assert pc._completed_bursts==1 and len(delivered)==1
        assert delivered[0]['kind']=='greeting'
        assert pc.store.call('profiles')==[]
        await pc._burst('gesture');assert len(delivered)==1
        await pc.close();await camera.close()
    asyncio.run(run())


def test_voice_interrupt_revokes_training_and_settles_producer(native_service,tmp_path):
    producer,_,client,_=native_service
    async def run():
        paths=KadencePaths.for_root(tmp_path/'host');ensure_schema(paths)
        camera=CameraManager(None,config=CameraConfig(address='127.0.0.1'))
        camera.unitv2=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=client.port))
        pc=PerceptionController(camera,paths,lambda *a:None,None,lambda:False)
        opened=await pc.open_native_training()
        assert '/native/open#' in opened['url'] and camera.unitv2.web_session
        await pc.interrupt()
        assert not camera.unitv2.web_session and producer.status()['stop_confirmed']
        await camera.close()
    asyncio.run(run())


def test_interrupted_native_save_restores_verified_pair_after_restart(tmp_path):
    seed(tmp_path)
    producer=bridge.Producer([],str(tmp_path))
    manager=native.NativeBridge(producer,bridge.CameraError,tmp_path,DEVICE)
    before={name:(tmp_path/'data'/name).read_bytes() for name in (native.INFO,native.FEATURES)}
    manager.backup()
    native.atomic_file(tmp_path/native.JOURNAL,json.dumps(manager.backup_record).encode())
    (tmp_path/'data'/native.FEATURES).write_bytes(b'partial interrupted write')
    native.recover_save(tmp_path)
    assert all((tmp_path/'data'/name).read_bytes()==data for name,data in before.items())
    assert not (tmp_path/native.JOURNAL).exists()
    assert native.catalog(tmp_path)['profiles'][0]['name']==NAME


def test_native_cancel_interrupts_socket_and_reaps_child(native_service):
    import time
    producer,_,client,root=native_service
    (root/'scene').write_text('silent')
    async def run():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=client.port))
        task=asyncio.create_task(owner.native_observe('127.0.0.1'))
        for _ in range(100):
            if producer.process:break
            await asyncio.sleep(.01)
        await asyncio.sleep(.1)
        started=time.monotonic();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert time.monotonic()-started<2 and producer.status()['stop_confirmed']
        await owner.close()
    asyncio.run(run())


def test_keep_ready_switches_native_and_camera_without_competing_producers(native_service):
    producer,_,client,_=native_service
    async def run():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=client.port))
        await owner.control_mode('KEEP_READY','127.0.0.1')
        first=producer.process
        result=await owner.native_observe('127.0.0.1')
        assert result['result']['num']==1 and first.poll() is not None
        second=producer.process
        await owner.capture('127.0.0.1')
        assert second.poll() is not None and producer.mode=='camera'
        assert producer.starts==3 and producer.stops==2
        await owner.close();assert producer.status()['stop_confirmed']
    asyncio.run(run())
