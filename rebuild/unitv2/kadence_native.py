"""Bridge to M5Stack's original on-device Face Recognition executable and UI.

No recognition model or face feature leaves the UnitV2. Python 3.8 stdlib only.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import time
import uuid

FACE_SHA256 = '00012bd3cda05f4fc482542830822f9bb15fe3c1a23794a106edf206ec13fd99'
INFO = 'face_recognition_info.json'
FEATURES = 'face_recognition_features.dat'
JOURNAL = 'kadence-native-save.json'
BUNDLE = ('kadence_unitv2.py', 'kadence_native.py', 'native_faces.html', 'native_faces.js')
ASSETS = {'/static/js/jquery.min.js', '/static/js/bin/face_recognition.js', '/static/js/core/post.server.js'}


def catalog(root):
    """Read the factory pair, validate it, return metadata only. Never repair it."""
    directory = Path(root) / 'data'
    info, features = directory / INFO, directory / FEATURES
    if directory.is_symlink() or info.is_symlink() or features.is_symlink():
        raise ValueError('Native profile location is not supported.')
    if not info.exists() and not features.exists(): raw, blob, faces = b'{}', b'', []
    else:
        if not info.is_file() or not features.is_file() or info.stat().st_size > 8192 or features.stat().st_size > 32*512:
            raise ValueError('Native profile files are incomplete; existing files were kept.')
        raw, blob = info.read_bytes(), features.read_bytes()
        doc = json.loads(raw)
        faces = doc.get('faces', []) if isinstance(doc, dict) else None
        if not isinstance(faces, list) or len(faces) > 32 or len(blob) != len(faces)*512:
            raise ValueError('Native profile files disagree; existing files were kept.')
    names, result = set(), []
    for index, face in enumerate(faces):
        name = face.get('name') if isinstance(face, dict) else None
        if not valid_name(name) or name.casefold() in names:
            raise ValueError('Native profiles need distinct valid names; review them on the UnitV2.')
        names.add(name.casefold())
        vector = struct.unpack('<128f', blob[index*512:(index+1)*512])
        if not all(math.isfinite(v) for v in vector) or sum(v*v for v in vector) < 1e-12:
            raise ValueError('Native profile features are invalid; existing files were kept.')
        result.append({'native_id': index, 'name': name})
    return {'profiles': result, 'revision': hashlib.sha256(raw+blob).hexdigest()}


def valid_name(name):
    return (isinstance(name, str) and 0 < len(name.encode('utf-8')) <= 80 and name == name.strip()
            and name.casefold() != 'unidentified' and not any(ord(c) < 32 for c in name))


def atomic_file(path, data):
    temporary = path.with_name(path.name+'.native-'+uuid.uuid4().hex+'.tmp')
    fd = os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(str(temporary),str(path))
        sync_directory(path.parent)
    finally:
        if temporary.exists(): temporary.unlink()


def sync_directory(path):
    if os.name == 'nt': return  # UnitV2 is Linux; Windows only runs the protocol tests.
    fd = os.open(str(path),os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def recover_save(root):
    """Roll back only our interrupted native save after its producer has exited."""
    root = Path(root)
    marker = root/JOURNAL
    if not marker.exists(): return
    if marker.is_symlink() or marker.stat().st_size>2048: raise ValueError('Invalid native save journal')
    record = json.loads(marker.read_text())
    folder = record.get('backup','')
    if not isinstance(folder,str) or not re.fullmatch('[0-9a-f]{32}',folder): raise ValueError('Invalid native backup')
    backup = root/'kadence-native-backups'/folder
    if backup.is_symlink() or backup.parent.is_symlink(): raise ValueError('Invalid native backup')
    files = record.get('files')
    if not isinstance(files,dict) or set(files)!={INFO,FEATURES}: raise ValueError('Invalid native backup')
    originals = {}
    for name in (INFO,FEATURES):
        if (root/'data'/name).is_symlink() or (root/'data').is_symlink(): raise ValueError('Invalid native data path')
        digest = files[name]
        if digest is None: originals[name] = None;continue
        source = backup/name
        if source.is_symlink() or source.stat().st_size>32*512: raise ValueError('Invalid native backup')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Native backup checksum differs')
        originals[name] = raw
    for name,raw in originals.items():
        target = root/'data'/name
        if raw is None:
            if target.exists(): target.unlink()
        else: atomic_file(target,raw)
    sync_directory(root/'data')
    marker.unlink();sync_directory(root)


class NativeBridge:
    def __init__(self, producer, error, root, device_id, *, command=None):
        self.p, self.Error, self.root = producer, error, Path(root)
        self.device_id = device_id
        self.command = command or [str(self.root / 'bin' / 'face_recognition')]
        self.web_token = self.web_cookie = None
        self.browser_seen = 0
        self.report = None
        self.report_seq = 0
        self.report_at = 0
        self.msg = ''
        self.msg_seq = 0
        self.training = False
        self.accepted = 0
        self.dirty = False
        self.save_message = 'Profiles are saved on the UnitV2.'
        self.memory_names = []
        self.backed_up = False
        self.backup_record = None
        self.revision = ''
        producer.native = self

    def profiles(self):
        try: value = catalog(self.root)
        except (ValueError, OSError, KeyError, TypeError): raise self.Error('native_profiles_invalid', 503)
        return dict(value, device_id=self.device_id)

    def prepare(self):
        value = self.profiles()
        self.memory_names = [p['name'] for p in value['profiles']]
        self.revision = value['revision']
        self.report, self.report_at = None, 0
        self.training = self.dirty = False
        self.accepted = 0
        return self.command

    def receive(self, doc):
        # Called under the producer's condition lock, exclusively from its reader.
        now = self.p.clock()
        if isinstance(doc.get('msg'), str):
            self.msg, self.msg_seq = doc['msg'][:250], self.msg_seq+1
        if doc.get('running') == 'Face Recognition':
            if self.training and doc.get('status') in {'training', 'missing'}:
                self.report = {k:doc[k] for k in ('status','x','y','w','h','prob','name') if k in doc}
                if doc['status'] == 'training': self.accepted += 1
                self.report_seq += 1
                self.report_at = now
            elif not self.training and type(doc.get('num')) is int and isinstance(doc.get('face'), list):
                faces = doc['face']
                if not 0 <= doc['num'] <= 16 or len(faces) != doc['num']: return
                self.report = {'num':doc['num'], 'face':faces}
                self.report_seq += 1
                self.report_at = now
        # The factory emits render:0 when the last face disappears, not num:0.
        if doc.get('render') == 0 and not self.training:
            self.report = {'num':0, 'face':[]}
            self.report_seq += 1
            self.report_at = now
        self.p.changed.notify_all()

    def image_ready(self):
        # Empty frames can follow the one-shot render:0. Never recycle a positive
        # identity from a previous frame if the executable stops reporting faces.
        if self.report is None or (not self.training and self.report.get('num') == 0):
            self.report = {'num':0, 'face':[]}
            self.report_seq += 1
            self.report_at = self.p.clock()

    def observation(self, lease, timeout=8):
        with self.p.changed:
            self.require_lease(lease)
            self.p.expires = self.p.clock()+30
            after, frame_after = self.report_seq, self.p.sequence
            deadline = self.p.clock()+timeout
            while True:
                self.require_lease(lease)
                if self.training: raise self.Error('native_training_active')
                if (self.report_seq > after and self.p.sequence > frame_after and self.p.frame
                        and self.p.clock()-self.report_at < 2 and self.p.clock()-self.p.frame_at < 1):
                    return dict(self.p.status(), device_id=self.device_id, revision=self.revision,
                        result=self.report, result_sequence=self.report_seq,
                        jpeg=base64.b64encode(self.p.frame).decode('ascii'))
                left = deadline-self.p.clock()
                if left <= 0: raise self.Error('native_result_timeout', 504)
                self.p.changed.wait(min(left,.1))

    def require_lease(self, lease):
        if (not lease or lease != self.p.lease or self.p.mode != 'faces' or self.p.state in {'STOPPED','STOPPING','FAULT'}
                or self.p.clock() >= self.p.expires): raise self.Error('native_session_ended')

    def open_web(self, lease):
        self.p.start(lease, 'faces')
        with self.p.lock:
            if self.web_token or self.web_cookie: raise self.Error('native_training_active')
            self.web_token = uuid.uuid4().hex
            self.browser_seen = self.p.clock()
            self.backed_up = False
            self.save_message = 'Select a saved profile or Add one, then Train. Save commits it onboard.'
            return dict(self.p.status(), ticket=self.web_token)

    def exchange(self, token):
        with self.p.lock:
            if not self.web_token or token != self.web_token or self.browser_expired():
                raise self.Error('native_session_ended', 401)
            self.require_lease(self.p.lease)
            self.web_token = None
            self.web_cookie = uuid.uuid4().hex
            self.browser_seen = self.p.clock()
            return self.web_cookie

    def authorize(self, cookie):
        with self.p.lock:
            if not self.web_cookie or cookie != self.web_cookie or self.browser_expired():
                raise self.Error('native_session_ended', 401)
            self.require_lease(self.p.lease)
            return self.p.lease

    def browser_expired(self):
        return bool((self.web_cookie or self.web_token) and self.p.clock()-self.browser_seen >= 30)

    def renew(self, lease):
        with self.p.lock:
            self.require_lease(lease)
            if self.browser_expired() or not (self.web_cookie or self.web_token): raise self.Error('native_session_ended')
            self.p.expires = self.p.clock()+30
            return self.p.status()

    def stopped(self):
        try: recover_save(self.root)
        except (ValueError,OSError): raise self.Error('native_save_recovery_required',503)
        self.web_token = self.web_cookie = None
        self.report = None
        self.training = False
        self.dirty = False

    def web_state(self, cookie):
        with self.p.lock:
            self.authorize(cookie)
            self.browser_seen = self.p.clock()
            fresh = self.report if self.report and self.p.clock()-self.report_at < 2 else {}
            return {'training':self.training, 'accepted':self.accepted, 'unsaved':self.dirty,
                    'message':self.save_message, 'result':fresh}

    def backup(self):
        if self.backed_up: return
        self.profiles()  # Refuse to overwrite a damaged existing pair.
        folder = self.root / 'kadence-native-backups' / uuid.uuid4().hex
        folder.mkdir(parents=True, mode=0o700)
        self.backup_record = {'backup':folder.name,'files':{}}
        for name in (INFO, FEATURES):
            source = self.root/'data'/name
            self.backup_record['files'][name] = None
            if source.exists():
                shutil.copyfile(str(self.root/'data'/name), str(folder/name))
                os.chmod(str(folder/name),0o600)
                with (folder/name).open('rb+') as file: os.fsync(file.fileno())
                self.backup_record['files'][name] = hashlib.sha256(source.read_bytes()).hexdigest()
        sync_directory(folder);sync_directory(folder.parent)
        self.backed_up = True

    def web_command(self, cookie, doc):
        operation = doc.get('operation')
        if operation not in {'train','stoptrain','saverun'}: raise self.Error('native_operation_not_supported',400)
        with self.p.control:
            with self.p.changed:
                lease = self.authorize(cookie)
                if operation == 'train':
                    index, name = doc.get('face_id'), doc.get('name')
                    if type(index) is not int or not 0 <= index <= len(self.memory_names) or index >= 10 or not valid_name(name):
                        raise self.Error('native_profile_invalid',400)
                    if any(n.casefold()==name.casefold() for i,n in enumerate(self.memory_names) if i != index):
                        raise self.Error('native_name_already_saved',400)
                    if self.dirty: raise self.Error('save_or_finish_current_training_first')
                    # The factory learns the largest face; refuse a known group.
                    if self.report and self.report.get('num',0)>1: raise self.Error('one_person_at_a_time')
                    self.backup()
                    if index == len(self.memory_names): self.memory_names.append(name)
                    else: self.memory_names[index] = name
                    self.training, self.dirty, self.accepted = True, True, 0
                    self.report = None
                    self.save_message = 'Training on UnitV2. Move gently; no fixed pose count. Stop, then Save when ready.'
                    payload = {'config':'web_update_data','operation':'train','face_id':index,'name':name}
                    expected = 'Training '+name
                else:
                    if operation == 'saverun' and self.dirty and self.accepted < 1:
                        raise self.Error('no_native_training_sample_yet')
                    payload = {'config':'web_update_data','operation':operation}
                    expected = 'Faces saved.' if operation=='saverun' else 'Exit training mode.'
                    if operation=='saverun' and not (self.root/JOURNAL).exists():
                        self.backup()
                        atomic_file(self.root/JOURNAL,json.dumps(self.backup_record).encode())
                prior = self.msg_seq
                prior_stat = self._file_stamp()
                self.p.process.stdin.write((json.dumps(payload)+'\r\n').encode('utf-8'))
                self.p.process.stdin.flush()
                deadline = self.p.clock()+6
                while self.msg_seq <= prior or self.msg != expected:
                    self.require_lease(lease)
                    left = deadline-self.p.clock()
                    if left <= 0: raise self.Error('native_command_timeout',504)
                    self.p.changed.wait(min(left,.1))
                if operation != 'train':
                    self.training = False
                    self.report = None
            if operation == 'saverun':
                # The vendor acknowledges BEFORE writing both files. Verify the
                # actual pair, names and a completed write, not merely that message.
                while self.p.clock() < deadline:
                    self.require_lease(lease)
                    try:
                        value = self.profiles()
                        if ([p['name'] for p in value['profiles']] == self.memory_names
                                and self._file_stamp() != prior_stat):
                            for filename in (INFO, FEATURES):
                                with (self.root/'data'/filename).open('rb+') as file: os.fsync(file.fileno())
                            sync_directory(self.root/'data')
                            (self.root/JOURNAL).unlink();sync_directory(self.root)
                            with self.p.lock:
                                self.revision = value['revision']
                                self.dirty = False
                                self.backed_up = False
                                self.save_message = '{} profile(s) saved and verified on the UnitV2.'.format(len(value['profiles']))
                            return {'message':self.save_message}
                    except (self.Error, OSError): pass
                    time.sleep(.05)
                raise self.Error('native_save_not_verified',503)
            return {'message':self.save_message if operation=='train' else 'Training stopped. Click Save to keep these features onboard.'}

    def _file_stamp(self):
        result = []
        for name in (INFO, FEATURES):
            try:
                stat = (self.root/'data'/name).stat()
                result.append((stat.st_mtime_ns,stat.st_size))
            except FileNotFoundError: result.append(None)
        return result
