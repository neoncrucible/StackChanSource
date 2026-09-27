"""Interpret native UnitV2 identities without a second PC face matcher."""
from collections import Counter, deque
from dataclasses import dataclass
import base64
import math
import re
import time
import uuid

from .camera_manager import CameraFrame, decode_jpeg, settled_thread
from .face_sequence import nearby


def validate_catalog(value):
    if not isinstance(value,dict) or not re.fullmatch('[0-9a-f]{32}',str(value.get('device_id',''))) or not re.fullmatch('[0-9a-f]{64}',str(value.get('revision',''))):
        raise ValueError('Invalid UnitV2 profile catalog.')
    profiles = value.get('profiles')
    if not isinstance(profiles,list) or len(profiles)>32: raise ValueError('Invalid UnitV2 profile catalog.')
    names = set()
    for index,p in enumerate(profiles):
        name=p.get('name') if isinstance(p,dict) else None
        if (not isinstance(name,str) or not 0<len(name.encode('utf-8'))<=80 or name!=name.strip()
                or name.casefold() in names or name.casefold()=='unidentified' or any(ord(c)<32 for c in name)
                or type(p.get('native_id')) is not int or p['native_id']!=index):
            raise ValueError('Invalid or duplicate UnitV2 profile name.')
        names.add(name.casefold())
    return value


@dataclass(frozen=True)
class NativeFace:
    box: tuple
    native_name: str
    score: float | None
    quality: float
    embedding: tuple = ()  # No biometric vector is transferred to the PC.


def read_faces(result):
    if not isinstance(result,dict) or type(result.get('num')) is not int or not 0<=result['num']<=16:
        raise ValueError('Invalid native face result.')
    rows=result.get('face')
    if not isinstance(rows,list) or len(rows)!=result['num']: raise ValueError('Invalid native face result.')
    faces=[]
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Invalid native face result.')
        numbers=[row.get(k) for k in ('x','y','w','h','prob')]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in numbers): raise ValueError('Invalid native face geometry.')
        x,y,w,h,quality=numbers
        if not (0<=x<640 and 0<=y<480 and 0<w<=640-x+1 and 0<h<=480-y+1 and 0<=quality<=1):
            raise ValueError('Invalid native face geometry.')
        name=row.get('name')
        score=row.get('match_prob')
        if not isinstance(name,str) or len(name.encode('utf-8'))>80: raise ValueError('Invalid native face identity.')
        if score is not None and (type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1):
            raise ValueError('Invalid native match score.')
        faces.append(NativeFace((x/640,y/480,w/640,h/480),name,score,quality))
    return faces


async def native_frame(camera, catalog):
    camera.check()
    generation=camera.generation
    if camera.unitv2.mode=='STOPPED': raise RuntimeError('UnitV2 is stopped. Select ON DEMAND first.')
    result=await camera.unitv2.native_observe(camera.config.address)
    camera.check(generation)
    if result.get('device_id')!=catalog['device_id'] or result.get('revision')!=catalog['revision']:
        raise RuntimeError('UnitV2 profiles changed during this check. Refresh Profiles and retry.')
    faces=read_faces(result.get('result'))
    encoded=result.get('jpeg')
    if not isinstance(encoded,str) or len(encoded)>2800000: raise ValueError('Invalid UnitV2 preview.')
    raw=base64.b64decode(encoded,validate=True)
    png,width,height,qr=await settled_thread(decode_jpeg,raw)
    camera.check(generation)
    frame=CameraFrame(str(uuid.uuid4()),str(uuid.uuid4()),'unitv2-camera',png,width,height,time.time(),0,generation,tuple(qr))
    report={'detected':len(faces),'usable':len(faces),'small':0,'blurred':0}
    return frame,faces,report


class NativeSequence:
    """Use M5Stack's >0.5 match rule and require two agreeing fresh observations.

    Spatial continuity and duplicate identities prevent cross-person vote reuse.
    Scores stay native similarities; no translation to SFace or probability.
    """
    def __init__(self, profiles):
        self.profiles=profiles
        self.current=[]
        self.tracks=[]
        self.index=0

    @property
    def confirmed(self): return {t['person'] for t in self.current if t['person']}

    def update(self, faces):
        self.index+=1
        matches=[self.profiles.get(f.native_name) if f.score is not None and f.score>.5 else None for f in faces]
        counts=Counter(p for p in matches if p)
        used=set(); current=[]
        for face,person in zip(faces,matches):
            duplicate=person and counts[person]>1
            reason='duplicate_identity' if duplicate else 'candidate' if person else 'no_profiles' if not self.profiles else 'below_threshold'
            if duplicate: person=None
            possible=[(i,t) for i,t in enumerate(self.tracks) if i not in used and self.index-t['index']<=2 and nearby(face,t['face'])]
            if len(possible)==1:
                i,track=possible[0];used.add(i)
            else: track={'votes':deque(maxlen=3),'seen':0}
            track['votes'].append(person)
            hits=sum(v==person for v in track['votes']) if person else 0
            conflict=any(v and v!=person for v in track['votes'])
            confirmed=person if person and hits>=2 and not conflict else None
            detail={'person':person,'status':'ambiguous' if duplicate else 'candidate' if person else 'unresolved',
                'reason':reason,'score':face.score,'threshold':.5,'gap':None,'margin':0}
            track.update(face=face,person=confirmed,match=detail,seen=track['seen']+1,index=self.index,hits=hits,
                identity='confirmed' if confirmed else 'ambiguous' if conflict or duplicate else 'unresolved')
            current.append(track)
        self.tracks=current+[t for i,t in enumerate(self.tracks) if i not in used and t not in current and self.index-t['index']<=2]
        self.tracks=self.tracks[:16]
        self.current=current
        return current
