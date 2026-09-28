"""Shared home controls adjacent to Tracking."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QPushButton
from PySide6.QtCore import Qt


class MotionPanel(QWidget):
    def __init__(self,send):
        super().__init__();self.send=send
        layout=QVBoxLayout(self)
        self.status=QLabel('Shared home has not been set.');self.status.setWordWrap(True);layout.addWidget(self.status)
        note=QLabel('Choose a pose, then SET HOME. This moves the head, verifies completion and torque release, and saves one home used by Motion and Tracking. It does not change servo calibration.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();self.yaw=QSpinBox();self.yaw.setRange(-32,32);self.yaw.setSuffix('° yaw')
        self.pitch=QSpinBox();self.pitch.setRange(3,87);self.pitch.setValue(30);self.pitch.setSuffix('° pitch')
        row.addWidget(self.yaw);row.addWidget(self.pitch);layout.addLayout(row)
        for text,action in [('MOVE TO POSE','motion_move'),('SET HOME','motion_set_home'),('HOME','motion_home'),('STOP / DISARM','motion_stop')]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,a=action:self.command(a));layout.addWidget(b)
        label=QLabel('Home persists across restarts. Nothing moves automatically at startup. Stop prevents further moves; an issued move settles before torque is released. The displayed pose is the last acknowledged target, not live telemetry.');label.setWordWrap(True);layout.addWidget(label);layout.addStretch()
        self.loaded=False

    def command(self,action):
        args={'yaw':self.yaw.value()*10,'pitch':self.pitch.value()*10} if action in {'motion_set_home','motion_move'} else {}
        def done(value):
            if not value.get('ok'):self.status.setText(value.get('message','Motion failed.'))
        self.send(action,args,done,timeout=20)

    def update_status(self,data):
        home=data.get('home',{'yaw':0,'pitch':300})
        if not self.loaded:
            self.yaw.setValue(round(home['yaw']/10));self.pitch.setValue(round(home['pitch']/10));self.loaded=True
        self.status.setText(f"Shared home: {home['yaw']/10:g}° yaw / {home['pitch']/10:g}° pitch · {'SAVED' if data.get('saved') else 'NOT SET'}\n{data.get('message','')}")
