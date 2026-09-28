"""Compact controls for the verified UnitV2 factory algorithms."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QPlainTextEdit,QSpinBox
import base64

MODES=(('Shape recognition','shape_detector'),('Colour tracking','color_tracker'),
       ('Motion detection','motion_tracker'),('Code detection','code_detector'),
       ('Object recognition','object_recognition'),('Face detection','face_detector'),
       ('Lane tracking','lane_line_tracker'),('Online classifier','online_classifier'),
       ('Audio FFT','audio_fft'),('Shape matching','shape_matching'))

class FactoryVisionPanel(QWidget):
    def __init__(self,send):
        super().__init__(); self.send=send
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.mode=QComboBox()
        for label,key in MODES:self.mode.addItem(label,key)
        row=QHBoxLayout(); row.addWidget(self.mode)
        start=QPushButton('START FACTORY MODE'); start.setObjectName('primary'); start.clicked.connect(self.start)
        stop=QPushButton('STOP'); stop.clicked.connect(lambda:self.send('factory_stop'))
        row.addWidget(start);row.addWidget(stop);layout.addLayout(row)
        self.status=QLabel('Stopped. These are M5Stack’s onboard algorithms; no robot movement.')
        self.status.setObjectName('status'); self.status.setWordWrap(True);layout.addWidget(self.status)
        self.preview=QLabel('NO FACTORY PREVIEW');self.preview.setAlignment(Qt.AlignCenter);self.preview.setMinimumHeight(220);layout.addWidget(self.preview)
        self.result=QPlainTextEdit();self.result.setReadOnly(True);self.result.setMaximumHeight(120);layout.addWidget(self.result)
        colour=QHBoxLayout(); self.lab={}
        for key in ('l_min','l_max','a_min','a_max','b_min','b_max'):
            spin=QSpinBox();spin.setRange(0,255);spin.setValue(0 if key.endswith('_min') else 255);spin.setPrefix(key.replace('_',' ')+': ');spin.setMaximumWidth(110)
            self.lab[key]=spin;colour.addWidget(spin)
        apply_colour=QPushButton('APPLY LAB COLOUR');apply_colour.clicked.connect(self.apply_colour);colour.addWidget(apply_colour);layout.addLayout(colour)
        layout.addWidget(QLabel('Colour tracking uses the UnitV2 LAB colour thresholds. Shape recognition detects geometric contours. Shape matching and Online Classifier require their own training in the original UnitV2 web interface. Object Recognition requires an installed vendor model. Audio FFT uses UnitV2’s microphone and releases it on Stop.'))
        layout.addStretch()
    def start(self):
        self.send('factory_start',{'mode':self.mode.currentData()})
    def apply_colour(self):
        self.send('factory_config',{'config':{key:spin.value() for key,spin in self.lab.items()}})
    def update_status(self,data):
        self.status.setText(f"{data.get('state','UNKNOWN')} · {data.get('mode') or 'none'} · {data.get('message','')}")
    def frame(self,data):
        if not data:self.preview.setText('NO FACTORY PREVIEW');self.result.clear();return
        raw=data.get('png')
        if raw:
            pix=QPixmap();pix.loadFromData(base64.b64decode(raw,validate=True),'PNG');self.preview.setPixmap(pix.scaled(520,300,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        self.result.setPlainText(str(data.get('result',{})))
