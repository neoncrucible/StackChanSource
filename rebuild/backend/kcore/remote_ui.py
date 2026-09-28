"""Remote pairing and deliberate transport controls; no credential diagnostics."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit
from PySide6.QtCore import Qt


class RemotePanel(QWidget):
    def __init__(self,send,settings):
        super().__init__();self.send=send;self.settings=settings
        layout=QVBoxLayout(self)
        row=QHBoxLayout();row.addWidget(QLabel('ROBOT LINK'))
        tether=QPushButton('TETHERED');tether.setCheckable(True);tether.setChecked(True);tether.clicked.connect(lambda:tether.setChecked(True));tether.setStyleSheet('color: #64ff88; border: 1px solid #64ff88;');row.addWidget(tether)
        wireless=QPushButton('WIRELESS — LATER');wireless.setEnabled(False);row.addWidget(wireless);layout.addLayout(row)
        self.status=QLabel('Remote OFF');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);layout.addWidget(self.status)
        row=QHBoxLayout()
        for name,on in [('REMOTE OFF',False),('REMOTE ON',True)]:
            b=QPushButton(name);b.clicked.connect(lambda checked=False,v=on:self.configure(v));row.addWidget(b)
        layout.addLayout(row)
        row=QHBoxLayout();self.port=QLineEdit();self.port.setPlaceholderText('StickS3 USB port, e.g. COM7');self.port.setMaxLength(80);row.addWidget(self.port)
        b=QPushButton('PAIR STICK VIA USB');b.clicked.connect(self.pair);row.addWidget(b);layout.addLayout(row)
        note=QLabel('Flash the Stick remote firmware first. Pairing copies the saved Wi-Fi details and PC LAN address over its USB port. Unplug it after pairing. Remote starts OFF; turning it off discards an active capture. Gyro and wireless robot transport are reserved for a later update.');note.setWordWrap(True);layout.addWidget(note)

    def result(self,data):
        if not data.get('ok'):self.status.setText(data.get('message','Remote command failed.'))

    def configure(self,on):
        self.send('remote_config',{'enabled':on,'host':self.settings()['lan_host']},self.result,timeout=20)

    def pair(self):
        settings=self.settings()
        self.send('remote_pair',{'port':self.port.text().strip(),'ssid':settings['ssid'],
            'password':settings['wifi_password'],'host':settings['lan_host']},self.result,timeout=30)

    def update_status(self,data):
        endpoint=f"{data.get('host','')}:{data.get('port',8766)}"
        self.status.setText(f"Remote {'ON' if data.get('enabled') else 'OFF'} · {'CONNECTED' if data.get('connected') else 'disconnected'} · {'paired' if data.get('paired') else 'not paired'}\n{endpoint} · Mic {data.get('mic','idle')} · RSSI {data.get('rssi') if data.get('rssi') is not None else '—'} · {data.get('error','')}")
