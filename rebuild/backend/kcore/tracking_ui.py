"""Tracking tab and image-coordinate selection, independent of camera transport."""
from __future__ import annotations
import base64
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QSpinBox, QGroupBox


class TargetPreview(QWidget):
    selected = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320,240)
        self.setMaximumHeight(400)
        self.pixmap=QPixmap()
        self.sequence=None
        self.box=None
        self.anchor=self.end=None
        self.setCursor(Qt.CrossCursor)

    def frame(self, data):
        encoded=data.get('jpeg') or data.get('png')
        if not encoded:
            self.pixmap=QPixmap();self.sequence=None;self.box=None;self.anchor=self.end=None
        elif self.anchor is None:
            pixmap=QPixmap()
            if pixmap.loadFromData(base64.b64decode(encoded,validate=True)):
                self.pixmap=pixmap;self.sequence=data['sequence'];self.box=data.get('box')
        self.update()

    def image_rect(self):
        if self.pixmap.isNull(): return QRectF()
        size=self.pixmap.size().scaled(self.size(),Qt.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())

    def paintEvent(self, event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#060d08'))
        area=self.image_rect()
        if area.isEmpty():
            painter.setPen(QColor('#a6bdad'))
            painter.drawText(self.rect(),Qt.AlignCenter,'Say “track that”\nor name an object below.');return
        painter.drawPixmap(area.toRect(),self.pixmap)
        painter.setPen(QPen(QColor('#64ff88'),2))
        if self.box:
            x,y,w,h=self.box
            painter.drawRect(QRectF(area.x()+x/640*area.width(),area.y()+y/480*area.height(),w/640*area.width(),h/480*area.height()))
        if self.anchor is not None and self.end is not None:
            painter.setPen(QPen(QColor('#fff080'),2,Qt.DashLine))
            painter.drawRect(QRectF(self.anchor,self.end).normalized().intersected(area))

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton and self.image_rect().contains(event.position()):
            self.anchor=self.end=event.position();self.update()

    def mouseMoveEvent(self, event):
        if self.anchor is not None: self.end=event.position();self.update()

    def mouseReleaseEvent(self, event):
        if self.anchor is None: return
        area=self.image_rect()
        box=QRectF(self.anchor,event.position()).normalized().intersected(area)
        self.anchor=self.end=None
        if area.width()>0 and box.width()>=6 and box.height()>=6:
            values=[round((box.x()-area.x())/area.width()*1000),round((box.y()-area.y())/area.height()*1000),
                    round(box.width()/area.width()*1000),round(box.height()/area.height()*1000)]
            values[2]=min(values[2],1000-values[0]);values[3]=min(values[3],1000-values[1])
            self.selected.emit({'sequence':self.sequence,'region':values})
        self.update()


class TrackingPanel(QWidget):
    def __init__(self, send):
        super().__init__();self.transport=send
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        def text(value):
            item=QLabel(value);item.setWordWrap(True);item.setTextFormat(Qt.PlainText);return item
        def button(value,action,args=None):
            item=QPushButton(value);item.clicked.connect(lambda:self.send(action,args() if callable(args) else args or {}));return item
        def row(*items):
            holder=QWidget();box=QHBoxLayout(holder);box.setContentsMargins(0,0,0,0)
            for item in items:box.addWidget(item)
            return holder
        self.status=text('Say “track that”, “follow this pen” or “track something red”.')
        self.status.setObjectName('status');layout.addWidget(self.status)
        self.target=QLineEdit();self.target.setPlaceholderText('What should I follow?');self.target.setMaxLength(80)
        self.target.returnPressed.connect(lambda:self.send('tracking_find',{'target':self.target.text().strip() or 'that'}))
        layout.addWidget(row(self.target,
                             button('Track','tracking_find',lambda:{'target':self.target.text().strip() or 'that'}),
                             button('Stop','tracking_stop'),button('Preview','tracking_preview')))
        layout.addWidget(text('No box needed. Show one object clearly; gently move it when saying “track that”. Colour and clear moving targets can be selected locally. Other objects use your vision service.'))
        self.preview=TargetPreview();self.preview.selected.connect(lambda args:self.send('tracking_select',args))
        layout.addWidget(self.preview,1)
        group=QGroupBox('Head setup');box=QVBoxLayout(group)
        self.mounted=QCheckBox('UnitV2 is attached to the moving head; cables have room to move')
        box.addWidget(self.mounted)
        self.home_label=text('Shared home: set it in Motion.')
        self.flip_yaw=QCheckBox('Reverse horizontal');self.flip_pitch=QCheckBox('Reverse vertical')
        box.addWidget(row(self.home_label,self.flip_yaw,self.flip_pitch))
        box.addWidget(row(button('Save head setup','tracking_arm',self.arm_args),button('Return home','tracking_home')))
        box.addWidget(text('One-time setup moves to the shared home saved in Motion and remembers the mounting directions. Future “follow” requests position the head and select the target automatically. Test with a slow movement; reverse an axis if it turns away. Steps stay within ±18° horizontally and ±15° vertically of home.'))
        layout.addWidget(group)
        layout.addWidget(text('Conversation keeps the target and pauses head movement. Privacy, Stop, another camera action or disconnect ends tracking. A session lasts up to 15 minutes.'))
        layout.addWidget(text('Brief loss resumes only after the same object is verified again. If it stays out of view, show it clearly and say “track that”.'))

    def arm_args(self):
        return {'mounted':self.mounted.isChecked(),
                'yaw_sign':-1 if self.flip_yaw.isChecked() else 1,'pitch_sign':-1 if self.flip_pitch.isChecked() else 1}

    def send(self, action, args=None):
        def finished(response):
            if not response.get('ok'):
                self.status.setText(response.get('message','Tracking action failed.'))
        self.transport(action,args or {},finished,timeout=45)

    def update_status(self, data):
        self.status.setText(f"{data.get('state','STOPPED')} · HEAD {'ARMED' if data.get('armed') else 'DISARMED'} · {data.get('message','')}")
