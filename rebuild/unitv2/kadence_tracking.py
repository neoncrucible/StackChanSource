"""Original UnitV2 MOSSE tracker; each result belongs to exactly one JPEG.

Python 3.8 stdlib only. No identity inference, persistence or motor authority.
"""
import base64
import json
import math
from pathlib import Path

TRACKER_SHA256 = '0cec301c02f8ab75bccedeedafef38758f3bf1ff931624683609b3cf315ed112'


def valid_roi(value):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        return False
    x, y, w, h = value
    return 0 <= x < 640 and 0 <= y < 480 and 8 <= w <= 640 and 8 <= h <= 480 and x+w <= 640 and y+h <= 480


class TrackingBridge:
    def __init__(self, producer, error, root, *, command=None):
        self.p, self.Error = producer, error
        self.command = command or [str(Path(root)/'bin'/'target_tracker')]
        self.pending = self.box = None
        self.epoch = 0
        self.selected = False
        self.ack = 0
        self.setting = False
        producer.tracking = self

    def prepare(self):
        self.pending = self.box = None
        self.selected = False
        self.epoch += 1
        return self.command

    def receive(self, doc):
        if doc.get('msg') == 'ROI updated.':
            self.ack += 1
            self.p.changed.notify_all()
        if doc.get('running') != 'Target Tracker' or not self.selected or self.setting:
            return
        values = [doc.get(k) for k in ('x','y','w','h')]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values): return
        roi = [round(v) for v in values]
        if valid_roi(roi): self.pending = roi

    def image_ready(self):
        # Factory emits NO lost event. Absence of coordinates before this JPEG
        # is a loss; never carry the previous successful box forward.
        self.box, self.pending = self.pending, None

    def require(self, lease):
        if not lease or self.p.lease != lease or self.p.mode != 'tracking' or self.p.clock() >= self.p.expires:
            raise self.Error('tracking_session_ended')
        if self.p.state in {'STOPPED','STOPPING','FAULT'}: raise self.Error('tracking_session_ended')

    def select(self, lease, roi):
        if not valid_roi(roi): raise self.Error('invalid_tracking_region',400)
        # Serialize reinitialisation against Stop and another target change.
        with self.p.control, self.p.changed:
            self.require(lease)
            self.setting = True
            self.selected = False
            self.pending = self.box = None
            after, deadline = self.ack, self.p.clock()+4
            try:
                payload = dict(config='Target Tracker', **dict(zip(('x','y','w','h'),roi)))
                self.p.process.stdin.write((json.dumps(payload)+'\r\n').encode())
                self.p.process.stdin.flush()
                while self.ack <= after:
                    self.require(lease)
                    left = deadline-self.p.clock()
                    if left <= 0: raise self.Error('tracking_selection_timeout',504)
                    self.p.changed.wait(min(left,.1))
                self.epoch += 1
                self.selected = True
                self.p.expires = self.p.clock()+30
                return dict(self.p.status(), target_epoch=self.epoch)
            except (OSError,ValueError):
                raise self.Error('tracking_selection_failed',503)
            finally:
                self.setting = False

    def observation(self, lease):
        with self.p.changed:
            self.require(lease)
            self.p.expires = self.p.clock()+30
            after, deadline = self.p.sequence, self.p.clock()+4
            while True:
                self.require(lease)
                if self.p.sequence > after and self.p.frame is not None and self.p.clock()-self.p.frame_at < .75:
                    return dict(self.p.status(), target_epoch=self.epoch, selected=self.selected,
                                box=self.box, image=base64.b64encode(self.p.frame).decode('ascii'))
                left = deadline-self.p.clock()
                if left <= 0: raise self.Error('tracking_frame_timeout',504)
                self.p.changed.wait(min(left,.1))

    def stopped(self):
        self.pending = self.box = None
        self.selected = False
        self.epoch += 1
