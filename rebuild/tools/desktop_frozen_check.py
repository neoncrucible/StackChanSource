"""Exercise the shipped executable's real pipe protocol without keys or hardware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import queue


def check(executable, expected_commit, *, offline=False):
    identity=json.loads(subprocess.check_output([str(executable),"--build-info"],text=True,timeout=30))
    assert identity["source_commit"]==expected_commit
    vision_fixture=Path(__file__).resolve().parents[1]/'tests'/'fixtures'/'vision-modern-response.json'
    vision=json.loads(subprocess.check_output([str(executable),'--vision-response-check',str(vision_fixture)],text=True,timeout=30))
    assert vision=={'parsed':True,'chars':50},vision
    print('DESKTOP_VISION_CONTRACT',json.dumps(vision),flush=True)
    fixture=Path(__file__).resolve().parents[1]/'tests'/'fixtures'/'stream-tone.mp3'
    decoded=json.loads(subprocess.check_output([str(executable),'--speech-decode-check',str(fixture)],text=True,timeout=30))
    assert decoded['before_eof'] and decoded['first_encoded_bytes']<=1152 and decoded['pcm_bytes']>128000,decoded
    print('DESKTOP_STREAM_DECODER',json.dumps(decoded),flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        process=subprocess.Popen([str(executable),'--worker'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            env={**os.environ,'KADENCE_DATA_DIR':tmp})
        output=queue.Queue()
        threading.Thread(target=lambda:[output.put(line) for line in process.stdout],daemon=True).start()
        threading.Thread(target=lambda:[print('DESKTOP_STDERR',line.rstrip(),flush=True) for line in process.stderr],daemon=True).start()
        def until(event,ident=None):
            for _ in range(30):
                try: raw=output.get(timeout=30)
                except queue.Empty:
                    code=process.poll()
                    if code is not None:
                        raise AssertionError(f"Frozen worker exited {code}; stderr: {process.stderr.read()[-4000:]}") from None
                    raise AssertionError("Frozen worker is alive but did not answer within 30 seconds") from None
                value=json.loads(raw)
                assert value['v']==1,value
                if value['event']=='model_check': print('DESKTOP_MODEL_STAGE',value['data'],flush=True)
                if value['event']==event and (ident is None or value['data'].get('id')==ident): return value['data']
            raise AssertionError('Expected control response missing')
        def send(ident,action,args):
            process.stdin.write(json.dumps({'v':1,'id':ident,'action':action,'args':args})+'\n'); process.stdin.flush()
        try:
            until('ready')
            send(1,'timezone',{'timezone':'Europe/London'}); assert until('result',1)['ok']
            send(2,'reminder_create',{'text':'Frozen fixture','when':'tomorrow at 09:00'}); assert until('result',2)['ok']
            send(3,'convert',{'value':1,'source':'in','target':'mm'}); assert until('result',3)['result']['result']==25.4
            if not offline:
                send(4,'speech_check',{}); speech=until('result',4)
                assert speech['ok'],speech
                assert speech['result']['pcm_bytes']>16000,speech
                print('DESKTOP_SPEECH',json.dumps(speech['result']),flush=True)
            send(5,'speech_check',{'local':True}); local=until('result',5)
            assert local['ok'] and local['result']['local_voice'],local
            assert local['result']['pcm_bytes']>16000,local
            print('DESKTOP_LOCAL_SPEECH',json.dumps(local['result']),flush=True)
            send(7,'face_model_check',{}); models=until('result',7)
            assert models['ok'] and models['result']['model_health']=='ready' and models['result']['faces']==0,models
            send(8,'camera_settings',{'privacy':True}); assert until('result',8)['ok']
            assert json.loads((Path(tmp)/'camera-settings.json').read_text())['privacy'] is True
            send(9,'face_profiles',{}); profiles=until('result',9)
            assert profiles['ok'] and profiles['result']['persons']==[] and profiles['result']['database'].endswith('kadence.sqlite3'),profiles
            send(10,'database_backup',{}); backup=until('result',10)
            assert backup['ok'] and Path(backup['result']['path']).is_file(),backup
            send(11,'local_tool',{'name':'camera_status'}); camera=until('result',11)
            assert camera['ok'] and camera['result']['ok'] and 'Privacy is on' in camera['result']['data']['spoken'],camera
            send(12,'vision_activity',{}); history=until('result',12)
            assert history['ok'] and history['result']['items']==[],history
            # Exercise photo reads/deletion through the actual frozen worker,
            # including the largest ordinary RGB PNG gallery wire payload.
            import base64, io
            from PIL import Image
            from kcore.perception_store import PerceptionStore
            photo=io.BytesIO();Image.frombytes('RGB',(256,256),os.urandom(256*256*3)).save(photo,format='PNG')
            store=PerceptionStore(Path(tmp)/'database'/'kadence.sqlite3')
            person=store.call('enroll',name='Frozen photo fixture',vectors=[(1.0,)+(0.0,)*127]*3,
                references=[{'png':photo.getvalue(),'source':'unitv2-camera','captured':1700000000.0}]*3)
            send(13,'face_photos',{'person_id':person}); photos=until('result',13)
            assert photos['ok'] and len(photos['result']['photos'])==3
            assert all(base64.b64decode(item['png_base64'])==photo.getvalue() for item in photos['result']['photos'])
            send(14,'face_forget',{'person_id':person}); assert until('result',14)['ok']
            assert not list((Path(tmp)/'media'/'face-profiles').glob('*.png'))
            send(6,'quit',{})
            assert until('closed')['clean'] is True
            assert process.wait(timeout=15)==0
            assert (Path(tmp)/'database'/'kadence.sqlite3').is_file()
            assert not process.stderr.read().strip()
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=5)
    fixtures=Path(__file__).resolve().parents[1]/'dist'/'face_fixtures'
    if not fixtures.is_dir():raise RuntimeError('Release face replay fixtures are missing')
    replay=subprocess.run([str(executable),'--face-replay-check',str(fixtures)],capture_output=True,text=True,timeout=45,check=True)
    records=[line.removeprefix('KADENCE_FACE_REPLAY ') for line in replay.stdout.splitlines() if line.startswith('KADENCE_FACE_REPLAY ')]
    assert len(records)==1,('Missing replay result',replay.stdout[-2000:],replay.stderr[-2000:])
    evidence=json.loads(records[0])
    assert evidence['matched_views']>evidence['three_sample_matches'] and evidence['different_people_rejected']==2,evidence
    print('DESKTOP_FACE_REPLAY',json.dumps(evidence),flush=True)
    print(f'DESKTOP_FROZEN PASS private_worker=1 timezone=1 persistence=1 utilities=1 profiles=1 profile_photos=1 photo_delete=1 backup=1 camera_voice_status=1 vision_history=1 online_speech_tested={int(not offline)} local_speech_pcm=1 clean_shutdown=1')


if __name__=='__main__': check(Path(sys.argv[1]),sys.argv[2],offline='--offline' in sys.argv[3:])
