"""Bounded local face evidence across fresh frames; never learn from recognition."""
from __future__ import annotations
from collections import Counter, deque
import math

from .local_faces import match_details, similarity


def nearby(a, b):
    ax, ay, aw, ah = a.box
    bx, by, bw, bh = b.box
    distance = math.hypot(ax+aw/2-bx-bw/2, ay+ah/2-by-bh/2)
    return distance <= max(.18, 2*max(aw, bw)) and .4 <= aw/max(bw, .001) <= 2.5


class FaceSequence:
    """Two agreeing profile matches in three observations, tolerant of short gaps.

    A profile can match different saved views. Requiring those views to also be
    near-identical to each other used to reject head turns. Spatial continuity,
    competing identities and duplicate candidates remain explicit gates.
    """
    def __init__(self, profiles):
        self.profiles = profiles
        self.tracks = []
        self.index = 0
        self.current = []

    def update(self, faces):
        self.index += 1
        details = [match_details(face.embedding, self.profiles) for face in faces]
        counts = Counter(d['person'] for d in details if d['person'])
        self.tracks = [t for t in self.tracks if self.index-t['index'] <= 2]
        used, current = set(), []
        for face, detail in zip(faces, details, strict=True):
            detail = dict(detail)
            if detail['person'] and counts[detail['person']] > 1:
                detail.update(person=None, status='ambiguous', reason='duplicate_identity')
            candidates = []
            for index, track in enumerate(self.tracks):
                if index in used or not nearby(face, track['face']): continue
                cosine = similarity(face.embedding, track['face'].embedding)
                same_profile = detail['person'] and detail['person'] == track['match']['person']
                if cosine >= .363 or same_profile:
                    candidates.append((float(cosine)+(.5 if same_profile else 0), index))
            candidates.sort(reverse=True)
            if candidates and (len(candidates)==1 or candidates[0][0]-candidates[1][0] >= .08):
                index = candidates[0][1]; used.add(index)
                track = self.tracks[index]
            else:
                track = {'votes':deque(maxlen=3), 'seen':0}
            track['votes'].append(detail['person'])
            track.update(face=face, match=detail, index=self.index, seen=track['seen']+1)
            person = detail['person']
            hits = sum(p == person for p in track['votes']) if person else 0
            conflict = any(p and p != person for p in track['votes'])
            confirmed = person if person and hits >= 2 and not conflict else None
            identity = 'confirmed' if confirmed else 'ambiguous' if conflict or detail['status']=='ambiguous' else 'unresolved'
            track.update(person=confirmed, identity=identity, hits=hits)
            current.append(track)
        self.tracks = current + [t for i,t in enumerate(self.tracks) if i not in used and t not in current]
        self.tracks = self.tracks[:16]
        self.current = current
        return current

    @property
    def confirmed(self):
        return {t['person'] for t in self.current if t['person']}


class LiveEnrollment:
    """Twenty samples from five measured views; no partial profile replacement."""
    PER_VIEW = 4
    VIEWS = ('front', 'turn_one', 'turn_other', 'tilt', 'distance')
    TOTAL = PER_VIEW * len(VIEWS)
    PROMPTS = (
        'Look at the camera; move your head slightly while keeping your face centred.',
        'Slowly turn a little toward either shoulder. Keep both eyes visible.',
        'Turn gently toward the other shoulder. Keep both eyes visible.',
        'Face forward and gently lift or lower your chin.',
        'Face forward and lean a little closer or farther away, at your usual seated position.',
    )

    def __init__(self):
        self.faces = []
        self.views = []
        self.anchor = None
        self.turn_sign = 0

    @property
    def stage(self): return min(len(self.faces)//self.PER_VIEW, len(self.VIEWS)-1)
    @property
    def done(self): return len(self.faces) == self.TOTAL
    @property
    def prompt(self): return self.PROMPTS[self.stage]

    def offer(self, faces, report):
        from .local_faces import quality_message
        if report.get('detected', len(faces)) > 1:
            return False, 'Only one person may be in view. Other faces are not added.'
        if not faces: return False, quality_message(report)
        face = faces[0]
        if self.anchor is None:
            if face.quality < .9:
                return False, 'Establish a clearer first view: face the camera and move a little closer.'
            if report.get('width',0) and face.box[2]*report['width'] < 64:
                return False, 'Move a little closer for the starting view; distance views come later.'
            if abs(face.yaw) > .18:
                return False, 'Face the camera directly to establish your starting view.'
            self.anchor = face
        else:
            # A fixed frontal anchor prevents gradually switching to another person.
            anchor_score = similarity(self.anchor.embedding, face.embedding)
            nearest = max(similarity(old.embedding, face.embedding) for old in self.faces)
            if anchor_score < .40 or nearest < .50:
                return False, 'Face continuity lost. Face the camera again; keep the same person in view.'
        stage = self.stage
        yaw = face.yaw-self.anchor.yaw
        if stage == 0 and abs(yaw) > .12: return False, self.PROMPTS[0]
        if stage == 1:
            if abs(yaw) < .14: return False, self.PROMPTS[1]
            if self.turn_sign and yaw*self.turn_sign < .14: return False, self.PROMPTS[1]
            self.turn_sign = 1 if yaw > 0 else -1
        if stage == 2 and yaw*self.turn_sign > -.14: return False, self.PROMPTS[2]
        if stage == 3 and (abs(yaw) > .16 or abs(face.pitch-self.anchor.pitch) < .10):
            return False, self.PROMPTS[3]
        ratio = face.box[2]/max(self.anchor.box[2], .001)
        if stage == 4 and (abs(yaw) > .16 or .82 < ratio < 1.22): return False, self.PROMPTS[4]
        # Don't fill a view with copies of the same embedding. Coverage still has
        # to be demonstrated from landmarks/scale, never inferred from a timer.
        current = self.faces[stage*self.PER_VIEW:]
        if any(similarity(old.embedding, face.embedding) > .998 for old in current):
            return False, 'View detected. Move a little within this angle for another distinct sample.'
        self.faces.append(face); self.views.append(self.VIEWS[stage])
        return True, 'All five views captured.' if self.done else self.prompt


def recognition_diagnostic(value):
    """No names, identifiers, embeddings, images or free-form error text."""
    safe = {}
    for key in ('frames','detected','usable','small','blurred','confirmed','stable','hits','samples','accepted','total'):
        item = value.get(key)
        if type(item) is int and 0 <= item <= 10000: safe[key] = item
    for key in ('score','gap','threshold','margin'):
        item = value.get(key)
        if type(item) in (int,float) and math.isfinite(item) and -2 <= item <= 2: safe[key] = round(item,4)
    options = {
        'kind':{'automatic','test','enrollment'},
        'reason':{'confirmed','no_face','no_usable_face','no_profiles','below_threshold','ambiguous','duplicate_identity','insufficient_evidence','capturing','saved','cancelled','failed','timeout','voice_busy','zone_clear'},
        'view':set(LiveEnrollment.VIEWS),
        'source':{'unitv2-camera','robot-camera'},
    }
    for key, allowed in options.items():
        item = value.get(key)
        if isinstance(item,str) and item in allowed: safe[key] = item
    return safe
