"""Allowlisted factory algorithms; no shell, model upload, or firmware API.

Executables remain on UnitV2. Digests are from the verified 2021 recovery image.
All state and results belong to the same revocable producer lease as faces.
"""
import base64
import hashlib
import json
from pathlib import Path

MODES = {
    'color_tracker': ('Color Tracker', 'bdd4b7f29bc8d76bd98e20179bef666908301e66661ca446648302af69d6ff3b'),
    'shape_detector': ('Shape Detector', 'afb467c9852cb783d9d1ca63029e2e2293fa45a66c9b42861a1592638ba5186b'),
    'shape_matching': ('Shape Matching', 'df494ddf1938ac5aeedd5d74c6df94ea89940cee5629f95909d914691ca285e2'),
    'motion_tracker': ('Motion Tracker', '3b3358561abd9b43b1ce0ab159ef1b4f925476ef99acd15355c0f5c3941d761d'),
    'code_detector': ('Code Detector', '760862251a94bebb1c046802b43680b74ea2815dfe029de2124380d9e28d5a30'),
    'object_recognition': ('Object Recognition', '7e478f8331b12b18b7ec06cce303337750abc899b87a011ac67fffc6a12652a0'),
    'face_detector': ('Face Detector', 'de713eded09a4797caecade29a5d68975df363960dbc324b51537d5e92aa3a5b'),
    'lane_line_tracker': ('Lane Line Tracker', 'e9e64bb0d100f45c066814de79dfeeba7947e7fe037e012beedf752d2585cc40'),
    'online_classifier': ('Online Classifier', 'b9928700725d57a872e4a0db6abd573ccd90cf0993b6828eb810688de92c39a6'),
    'audio_fft': ('Audio FFT', '56d13d22fc36d23e156e72a7b7048027e3c4208539ea360eb8d6c3259e9c5068'),
}


def configuration(mode, value):
    """Reject unknown fields before anything reaches a vendor parser."""
    if mode not in MODES or not isinstance(value, dict): raise ValueError('Invalid factory mode')
    keys = set(value)
    if mode in {'color_tracker', 'lane_line_tracker'}:
        if keys == {'x','y','w','h'}:
            from kadence_tracking import valid_roi
            if not valid_roi([value[k] for k in ('x','y','w','h')]): raise ValueError('Invalid colour region')
        elif keys == {'l_min','l_max','a_min','a_max','b_min','b_max'}:
            if any(type(v) is not int or not 0<=v<=255 for v in value.values()): raise ValueError('LAB values must be 0..255')
            if any(value[k+'_min']>value[k+'_max'] for k in ('l','a','b')): raise ValueError('LAB minimum exceeds maximum')
        elif keys == {'mode'} and value['mode'] in {'mask','normal'}: pass
        else: raise ValueError('Unsupported colour configuration')
    elif mode in {'motion_tracker','shape_detector'} and value == {'operation':'update'}: pass
    else: raise ValueError('Unsupported factory configuration')
    return dict(value, config=MODES[mode][0])


class FactoryBridge:
    def __init__(self, producer, error, root, *, commands=None):
        self.p, self.Error, self.root = producer, error, Path(root)
        self.commands = commands  # isolated real-child-process tests only
        self.mode = None
        self.pending = self.report = {}
        self.sequence = 0
        self.at = 0
        self.message = ''
        self.p.factory = self

    def catalog(self):
        result = []
        for mode,(name,digest) in MODES.items():
            path = self.root/'bin'/mode
            try: available = not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest
            except OSError: available = False
            result.append({'mode':mode,'name':name,'available':available})
        return result

    def prepare(self, mode):
        if mode not in MODES: raise self.Error('invalid_factory_mode',400)
        command = self.commands.get(mode) if self.commands else None
        if command is None:
            path = self.root/'bin'/mode
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=MODES[mode][1]:
                raise self.Error('factory_binary_unavailable',503)
            command = [str(path)]
        self.mode = mode
        self.pending = self.report = {}
        self.sequence = 0
        self.message = ''
        return command

    def require(self, lease):
        if not lease or lease != self.p.lease or self.p.mode != 'factory:'+str(self.mode) or self.p.state not in {'STARTING','RUNNING'} or self.p.clock()>=self.p.expires:
            raise self.Error('lease_not_active')

    def receive(self, doc):
        if doc.get('render') == 0: self.pending = {}
        if doc.get('running') != MODES[self.mode][0]: return
        if isinstance(doc.get('msg'),str): self.message=doc['msg'][:250]
        value = {k:v for k,v in doc.items() if k not in {'img','running','web','msg'}}
        try:
            if len(json.dumps(value,allow_nan=False))>60000: return
        except (ValueError,TypeError): return
        if value:
            self.pending = value
            if self.mode == 'audio_fft': self.image_ready()
        self.p.changed.notify_all()

    def image_ready(self):
        # Never carry positive detections across frames without a new report.
        self.report, self.pending = self.pending, {}
        self.sequence += 1
        self.at = self.p.clock()
        self.p.changed.notify_all()

    def configure(self, lease, value):
        try: command = configuration(self.mode,value)
        except ValueError: raise self.Error('invalid_factory_config',400)
        with self.p.control:
            with self.p.changed:
                self.require(lease)
                self.pending = self.report = {}
                self.message = ''
                try:
                    self.p.process.stdin.write((json.dumps(command)+'\r\n').encode())
                    self.p.process.stdin.flush()
                except (OSError,ValueError): raise self.Error('producer_write_failed',503)
                self.p.expires = self.p.clock()+30
                return dict(self.p.status(),message='Configuration sent; check the live result.')

    def observation(self, lease, timeout=8):
        with self.p.changed:
            self.require(lease)
            self.p.expires = self.p.clock()+30
            after,deadline = self.sequence,self.p.clock()+timeout
            while True:
                self.require(lease)
                if self.sequence>after and self.p.clock()-self.at<1:
                    image = base64.b64encode(self.p.frame).decode('ascii') if self.p.frame and self.mode!='audio_fft' else None
                    return dict(self.p.status(),result_sequence=self.sequence,result=self.report,image=image,message=self.message)
                left=deadline-self.p.clock()
                if left<=0: raise self.Error('factory_result_timeout',503)
                self.p.changed.wait(min(left,.2))

    def stopped(self):
        self.mode=None
        self.pending=self.report={}
        self.message=''
