"""Exercise the shipped executable's real pipe protocol without keys or hardware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import queue


def check(executable, expected_commit):
    identity=json.loads(subprocess.check_output([str(executable),"--build-info"],text=True,timeout=30))
    assert identity["source_commit"]==expected_commit
    with tempfile.TemporaryDirectory() as tmp:
        process=subprocess.Popen([str(executable),'--worker'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            env={**os.environ,'KADENCE_DATA_DIR':tmp})
        output=queue.Queue()
        threading.Thread(target=lambda:[output.put(line) for line in process.stdout],daemon=True).start()
        def until(event,ident=None):
            for _ in range(30):
                raw=output.get(timeout=30)
                value=json.loads(raw)
                assert value['v']==1,value
                if value['event']==event and (ident is None or value['data'].get('id')==ident): return value['data']
            raise AssertionError('Expected control response missing')
        def send(ident,action,args):
            process.stdin.write(json.dumps({'v':1,'id':ident,'action':action,'args':args})+'\n'); process.stdin.flush()
        try:
            until('ready')
            send(1,'timezone',{'timezone':'Europe/London'}); assert until('result',1)['ok']
            send(2,'reminder_create',{'text':'Frozen fixture','when':'tomorrow at 09:00'}); assert until('result',2)['ok']
            send(3,'convert',{'value':1,'source':'in','target':'mm'}); assert until('result',3)['result']['result']==25.4
            send(4,'speech_check',{}); speech=until('result',4)
            assert speech['ok'],speech
            assert speech['result']['pcm_bytes']>16000,speech
            print('DESKTOP_SPEECH',json.dumps(speech['result']),flush=True)
            send(5,'speech_check',{'local':True}); local=until('result',5)
            assert local['ok'] and local['result']['local_voice'],local
            assert local['result']['pcm_bytes']>16000,local
            print('DESKTOP_LOCAL_SPEECH',json.dumps(local['result']),flush=True)
            send(6,'quit',{})
            assert until('closed')['clean'] is True
            assert process.wait(timeout=15)==0
            assert (Path(tmp)/'context.sqlite3').is_file()
            assert not process.stderr.read().strip()
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=5)
    print('DESKTOP_FROZEN PASS private_worker=1 timezone=1 persistence=1 utilities=1 speech_pcm=1 local_speech_pcm=1 clean_shutdown=1')


if __name__=='__main__': check(Path(sys.argv[1]),sys.argv[2])
