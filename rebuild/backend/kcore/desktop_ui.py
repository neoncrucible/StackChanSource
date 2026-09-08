from __future__ import annotations

import base64
import json
import math
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QStackedWidget, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QSlider, QGroupBox, QFileDialog, QMessageBox, QSystemTrayIcon,
    QMenu, QScrollArea,
)

from .context_store import default_data_dir
from .credential_vault import CredentialVault
from .desktop_process import ControlProcess
from .workbench import UNITS
from .build_info import build_info

STYLE = """
QWidget { background: #050706; color: #d4dfd7; font-family: 'Cascadia Mono','Consolas','DejaVu Sans Mono'; font-size: 12px; }
QMainWindow { background: #050706; }
QLabel#brand { color: #b4ff8d; font-size: 24px; font-weight: bold; letter-spacing: 3px; }
QLabel#muted { color: #88968d; }
QLabel#title { font-size: 23px; color: #e0f2e5; font-weight: bold; }
QLabel#status { color: #b4ff8d; }
QFrame#rule { background: #263c2d; max-height: 1px; }
QFrame#rail { border-right: 1px solid #263c2d; }
QGroupBox { border: 1px solid #293c2f; margin-top: 15px; padding: 16px 12px 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #b4ff8d; }
QPushButton { background: #101a13; border: 1px solid #39523f; padding: 9px 13px; color: #d6eadb; }
QPushButton:hover { border-color: #b4ff8d; color: #b4ff8d; }
QPushButton:pressed, QPushButton:checked { background: #b4ff8d; color: #0b130b; border-color: #b4ff8d; }
QPushButton:disabled { color: #58635b; border-color: #253027; background: #0a0e0b; }
QPushButton#primary { background: #b4ff8d; color: #08100a; font-weight: bold; }
QPushButton#nav { text-align: left; border: none; padding: 14px 12px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: #0b110d; border: 1px solid #324c3a; padding: 7px; selection-background-color: #b4ff8d; selection-color: #08100a; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #b4ff8d; }
QComboBox::drop-down { border: none; width: 24px; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #789481; background: #0b110d; }
QCheckBox::indicator:checked { background: #b4ff8d; }
QTableWidget { background: #050706; border: 1px solid #293c2f; gridline-color: #1d2c22; selection-background-color: #23402c; }
QHeaderView::section { background: #111c15; color: #a6bdad; border: none; border-bottom: 1px solid #39523f; padding: 9px; }
QSlider::groove:horizontal { height: 4px; background: #304736; }
QSlider::sub-page:horizontal { background: #b4ff8d; }
QSlider::handle:horizontal { background: #b4ff8d; width: 13px; margin: -6px 0; }
QScrollBar:vertical { background: #0b110d; width: 10px; }
QScrollBar::handle:vertical { background: #39523f; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #19281e; color: #e0f2e5; border: 1px solid #b4ff8d; }
"""


def label(text, role=None):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    if role: item.setObjectName(role)
    return item


def button(text, callback, *, primary=False):
    item = QPushButton(text)
    item.clicked.connect(callback)
    if primary: item.setObjectName("primary")
    return item


def line(placeholder="", maximum=800):
    item = QLineEdit()
    item.setPlaceholderText(placeholder)
    item.setMaxLength(maximum)
    item.setClearButtonEnabled(True)
    return item


def row(*widgets):
    item = QWidget(); layout = QHBoxLayout(item); layout.setContentsMargins(0,0,0,0)
    for widget in widgets: layout.addWidget(widget)
    return item


def table(columns):
    item = QTableWidget(0, len(columns))
    item.setHorizontalHeaderLabels(columns)
    item.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    item.horizontalHeader().setStretchLastSection(True)
    item.verticalHeader().hide()
    item.setSelectionBehavior(QTableWidget.SelectRows)
    item.setSelectionMode(QTableWidget.SingleSelection)
    item.setEditTriggers(QTableWidget.NoEditTriggers)
    item.setWordWrap(False)
    item.setAlternatingRowColors(False)
    return item


class Avatar(QWidget):
    """Code-native companion emblem; activity follows acknowledged device state."""
    def __init__(self):
        super().__init__(); self.phase="idle"; self.epoch=time.monotonic()
        self.setMinimumSize(260,180)
        self.timer=QTimer(self); self.timer.setInterval(66); self.timer.timeout.connect(self.update); self.timer.start()
    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#050706"))
        p.translate(self.width()/2,self.height()/2-6)
        scale=min(self.width()/320,self.height()/215); p.scale(scale,scale)
        t=time.monotonic()-self.epoch
        blink=(t%5.8)>5.65; moving=self.phase in {"thinking","tool-working","camera"}
        glance=math.sin(t*.7)*5 if moving else math.sin(t*.3)*2
        p.setPen(QPen(QColor("#234731"),1))
        for x in (-136,136):
            sign=1 if x<0 else -1
            p.drawLine(x,-60,x+sign*15,-60); p.drawLine(x,-60,x,-45)
            p.drawLine(x,60,x+sign*15,60); p.drawLine(x,60,x,45)
        for cx in (-52,52):
            p.setPen(Qt.NoPen); p.setBrush(QColor("#143326")); p.drawRoundedRect(QRectF(cx-32,-40,64,57),20,20)
            p.setBrush(QColor("#a6ffbd")); h=4 if blink else 36
            p.drawRoundedRect(QRectF(cx-21+glance,-29+(36-h)/2,42,h),12,12)
            if not blink:
                p.setBrush(QColor("#f0fff4")); p.drawRoundedRect(QRectF(cx-14+glance,-23,6,10),3,3)
        p.setPen(QPen(QColor("#85dcad"),3,Qt.SolidLine,Qt.RoundCap))
        mouth=4+abs(math.sin(t*8))*9 if self.phase=="speaking" else 4
        p.drawArc(QRectF(-16,24,32,mouth*2),180*16,180*16)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, *, control=None, directory=None, load_credentials=True):
        super().__init__()
        self.directory=directory or default_data_dir(); self.directory.mkdir(parents=True,exist_ok=True)
        self.settings_path=self.directory/"desktop-settings.json"
        self.control=control or ControlProcess(self)
        self.control.event.connect(self.on_event)
        self.control.exited.connect(self._worker_exited)
        self.server_state="stopped"; self.robot_connected=False; self.quitting=False
        self.started_at=None; self.reminders=[]; self.projects=[]; self.nav=[]; self.entries=[]
        self.diagnostic=deque(maxlen=400); self._settings={}; self.snapshot_pixmap=None
        self.active_timezone="Europe/London"; self.timings={}
        self.setWindowTitle("Kadence • Control")
        self.resize(1160,800); self.setMinimumSize(980,690)
        self.setStyleSheet(STYLE)
        root=QWidget(); self.setCentralWidget(root); shell=QVBoxLayout(root); shell.setContentsMargins(24,18,24,14); shell.setSpacing(14)
        heading=QHBoxLayout(); heading.addWidget(label("KADENCE", "brand")); heading.addWidget(label("/  CONTROL", "muted")); heading.addStretch()
        self.clock=label("LOCAL CLOCK", "muted"); heading.addWidget(self.clock)
        shell.addLayout(heading)
        rule=QFrame(); rule.setObjectName("rule"); shell.addWidget(rule)
        controls=QHBoxLayout()
        self.server_label=label("SERVER  STOPPED", "status"); self.robot_label=label("ROBOT  DISCONNECTED", "muted")
        controls.addWidget(self.server_label); controls.addSpacing(22); controls.addWidget(self.robot_label); controls.addStretch()
        self.start_button=button("START SERVER",self.start_server,primary=True)
        self.stop_button=button("STOP",lambda:self.control.send("server_stop"))
        self.restart_button=button("RESTART",lambda:self.start_server(restart=True))
        for b in (self.start_button,self.stop_button,self.restart_button): controls.addWidget(b)
        shell.addLayout(controls)
        content=QHBoxLayout(); content.setSpacing(22)
        rail=QFrame(); rail.setObjectName("rail"); rail.setFixedWidth(175); sidebar=QVBoxLayout(rail); sidebar.setContentsMargins(0,6,14,0)
        self.pages=QStackedWidget()
        for index,(title,method) in enumerate((("01  OVERVIEW",self.overview_page),("02  REMINDERS",self.reminders_page),("03  WORKBENCH",self.workbench_page),("04  VISION",self.vision_page),("05  DEVICE / PLAY",self.device_page),("06  DIAGNOSTICS",self.diagnostics_page))):
            b=button(title,lambda checked=False,i=index:self.navigate(i)); b.setObjectName("nav"); b.setCheckable(True); self.nav.append(b); sidebar.addWidget(b)
            page=method(); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(page); self.pages.addWidget(scroll)
        sidebar.addStretch(); sidebar.addWidget(label("PRIVATE LAB\nLOCAL COMPANION", "muted"))
        info=build_info(); sidebar.addWidget(label(f"v{info['host_version']} / RC2\n{info['source_commit'][:12]}","muted"))
        self.tray_check=QCheckBox("Keep in tray"); sidebar.addWidget(self.tray_check)
        sidebar.addWidget(button("QUIT",self.quit_app))
        content.addWidget(rail); content.addWidget(self.pages,1); shell.addLayout(content,1)
        self.message=label("Local utilities are starting…", "muted"); self.message.setMinimumHeight(36); shell.addWidget(self.message)
        self.navigate(0)
        self._load_settings(load_credentials)
        self.timezone.editingFinished.connect(self.apply_timezone)
        self._make_tray()
        self.ticker=QTimer(self); self.ticker.setInterval(1000); self.ticker.timeout.connect(self.tick); self.ticker.start()
        self.update_controls(); self.tick()

    def page(self,title,subtitle):
        widget=QWidget(); layout=QVBoxLayout(widget); layout.setContentsMargins(0,4,4,8); layout.setSpacing(12)
        layout.addWidget(label(title,"title")); layout.addWidget(label(subtitle,"muted"))
        return widget,layout

    def overview_page(self):
        page,layout=self.page("A place for Kadence.","Voice, useful tools and a little company at your workbench.")
        top=QHBoxLayout(); self.avatar=Avatar(); top.addWidget(self.avatar,1)
        info=QVBoxLayout(); self.activity=label("READY WHEN YOU ARE", "status"); self.activity.setStyleSheet("font-size: 18px;")
        self.runtime_info=label("Server stopped. Local reminders work while this app is open.","muted")
        self.next_due=label("No scheduled reminders."); self.turn_info=label("Completed turns  0","muted")
        for w in (self.activity,self.runtime_info,self.next_due,self.turn_info): info.addWidget(w)
        info.addStretch(); top.addLayout(info,1); layout.addLayout(top)
        group=QGroupBox("CONNECTION & CREDENTIALS"); grid=QGridLayout(group)
        self.port=QComboBox(); self.port.setEditable(True); self.port.addItem("COM4")
        self.ssid=line("Wi-Fi network",32); self.lan=QComboBox(); self.lan.setEditable(True); self.lan.addItem("Auto-detect","")
        self.timezone=line("Europe/London",80); self.timezone.setText("Europe/London")
        self.capture=QSpinBox(); self.capture.setRange(2400,8000); self.capture.setSingleStep(600); self.capture.setValue(4800); self.capture.setSuffix(" ms")
        grid.addWidget(label("Robot port"),0,0); grid.addWidget(self.port,0,1); grid.addWidget(button("SCAN",self.scan_connections),0,2)
        grid.addWidget(label("Wi-Fi network"),1,0); grid.addWidget(self.ssid,1,1,1,2)
        grid.addWidget(label("PC LAN address"),2,0); grid.addWidget(self.lan,2,1,1,2)
        self.secret_fields={}
        for index,(key,title) in enumerate((("openai_api_key","OpenAI key"),("gemini_api_key","Gemini key"),("wifi_password","Wi-Fi password")),3):
            edit=line(title,1024 if key!="wifi_password" else 63); edit.setEchoMode(QLineEdit.Password)
            reveal=QPushButton("SHOW"); reveal.setCheckable(True)
            reveal.toggled.connect(lambda shown,e=edit,b=reveal:(e.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password),b.setText("HIDE" if shown else "SHOW")))
            self.secret_fields[key]=edit
            grid.addWidget(label(title),index,0); grid.addWidget(edit,index,1); grid.addWidget(reveal,index,2)
        self.remember=QCheckBox("Remember on this Windows account"); self.remember.setEnabled(os.name=="nt")
        grid.addWidget(self.remember,6,1); grid.addWidget(button("FORGET",self.forget_credentials),6,2)
        grid.addWidget(label("Timezone"),7,0); grid.addWidget(self.timezone,7,1); grid.addWidget(self.capture,7,2)
        layout.addWidget(group)
        layout.addWidget(label("Session-only credentials by default. SHOW reveals a field here; diagnostics never include it.","muted"))
        layout.addStretch()
        return page

    def reminders_page(self):
        page,layout=self.page("Remember the next thing.","Real dates, local time, stored deadlines. Keep Windows awake for alerts.")
        create=QGroupBox("NEW REMINDER"); grid=QGridLayout(create)
        self.reminder_text=line("Check the print, order filament, call someone…")
        self.reminder_when=line("tomorrow at 09:00  /  in twenty minutes  /  Friday at 7 pm",120)
        grid.addWidget(label("Remind me to"),0,0); grid.addWidget(self.reminder_text,0,1)
        grid.addWidget(label("When"),1,0); grid.addWidget(self.reminder_when,1,1)
        grid.addWidget(button("SCHEDULE",self.create_reminder,primary=True),1,2)
        self.reminder_question=label("Kadence will ask when a date or time needs clarification.","muted"); grid.addWidget(self.reminder_question,2,0,1,3)
        self.reminder_answer=line("Answer a date/time question here",120)
        self.answer_button=button("ANSWER",lambda:self.control.send("reminder_answer",{"answer":self.reminder_answer.text()},self.reminder_result))
        self.answer_button.setEnabled(False)
        grid.addWidget(self.reminder_answer,3,1); grid.addWidget(self.answer_button,3,2)
        layout.addWidget(create)
        self.reminder_table=table(["ID","State","When","Reminder"]); layout.addWidget(self.reminder_table,1)
        self.snooze_minutes=QSpinBox(); self.snooze_minutes.setRange(1,10080); self.snooze_minutes.setValue(5); self.snooze_minutes.setSuffix(" min")
        layout.addWidget(row(button("DISMISS",lambda:self.reminder_action("reminder_dismiss")),button("CANCEL",lambda:self.reminder_action("reminder_cancel")),self.snooze_minutes,button("SNOOZE",lambda:self.reminder_action("reminder_snooze")),button("START BREAK",lambda:self.reminder_action("break_start"))))
        self.focus_minutes=QSpinBox(); self.focus_minutes.setRange(1,180); self.focus_minutes.setValue(25); self.focus_minutes.setSuffix(" min")
        layout.addWidget(row(label("FOCUS SESSION", "status"),self.focus_minutes,button("BEGIN FOCUS",lambda:self.control.send("focus_start",{"minutes":self.focus_minutes.value()})),button("REFRESH",lambda:self.control.send("utilities"))))
        layout.addWidget(label("A completed focus session offers a five-minute break. Missed reminders stay visible; they are not replayed as a queue of speeches.","muted"))
        return page

    def workbench_page(self):
        page,layout=self.page("Your lab, in order.","Project notes, resumable checklists and calculations with explicit units.")
        self.project_select=QComboBox(); self.project_select.currentIndexChanged.connect(self.load_entries)
        self.project_name=line("New project name",80)
        layout.addWidget(row(self.project_select,self.project_name,button("CREATE PROJECT",lambda:self.control.send("project_add",{"name":self.project_name.text()}))))
        self.search=line("Search this project's notes and steps",120); self.search.returnPressed.connect(self.load_entries)
        layout.addWidget(row(self.search,button("SEARCH",self.load_entries)))
        self.entry_table=table(["ID","Type","State","Record"]); layout.addWidget(self.entry_table,1)
        self.entry_text=line("A short note or the next checklist step",800)
        layout.addWidget(self.entry_text)
        layout.addWidget(row(button("ADD NOTE",lambda:self.add_entry("note")),button("ADD STEP",lambda:self.add_entry("step")),button("MARK DONE",self.complete_entry),button("DELETE",self.delete_entry)))
        calculations=QGroupBox("CALCULATOR"); grid=QGridLayout(calculations)
        self.calc_mode=QComboBox(); self.calc_mode.addItems(["Arithmetic","Convert units","Ohm's law","Resistor bands"])
        self.calc_input=line("(12 + 3) * 4",180)
        self.calc_from=QComboBox(); self.calc_to=QComboBox()
        for box in (self.calc_from,self.calc_to): box.addItems(list(UNITS)); box.setEnabled(False)
        self.calc_hint=label("Arithmetic: + − * / % ** and parentheses.","muted")
        self.calc_mode.currentIndexChanged.connect(self.calc_changed)
        grid.addWidget(self.calc_mode,0,0); grid.addWidget(self.calc_input,0,1); grid.addWidget(button("CALCULATE",self.calculate),0,2)
        grid.addWidget(self.calc_from,1,0); grid.addWidget(self.calc_to,1,1); grid.addWidget(self.calc_hint,2,0,1,3)
        self.calc_result=label("Result appears here.","status"); grid.addWidget(self.calc_result,3,0,1,3)
        layout.addWidget(calculations)
        return page

    def vision_page(self):
        page,layout=self.page("Take a closer look.","One requested image. Local QR decoding; Gemini descriptions only when you ask.")
        self.preview=label("CAMERA OFF\n\nCapture a snapshot to begin.","muted"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumSize(480,290)
        self.preview.setStyleSheet("border: 1px solid #293c2f;"); layout.addWidget(self.preview,1)
        self.vision_question=line("What am I holding? Read the large label. What objects can you see?",500)
        layout.addWidget(self.vision_question)
        layout.addWidget(row(button("CAPTURE",lambda:self.control.send("camera_capture"),primary=True),button("DESCRIBE WITH GEMINI",lambda:self.control.send("camera_describe",{"question":self.vision_question.text() or "Describe the visible desk objects."})),button("CANCEL",lambda:self.control.send("media_cancel")),button("CLEAR",lambda:self.control.send("camera_clear"))))
        self.vision_result=QPlainTextEdit(); self.vision_result.setReadOnly(True); self.vision_result.setMaximumHeight(140); self.vision_result.setPlaceholderText("Description and decoded QR text appear here. QR text is never opened or executed."); layout.addWidget(self.vision_result)
        self.vision_project=QComboBox()
        layout.addWidget(row(self.vision_project,button("SAVE OBSERVATION",lambda:self.control.send("camera_save",{"project_id":self.vision_project.currentData()}))))
        layout.addWidget(label("Images remain temporary until SAVE OBSERVATION. Continuous tracking and familiar-person profiles are reserved for later qualification.","muted"))
        return page

    def device_page(self):
        page,layout=self.page("Light, sound and play.","Front-screen touch still starts or cancels a voice turn.")
        audio=QGroupBox("AUDIO"); grid=QGridLayout(audio)
        self.volume=QSlider(Qt.Horizontal); self.volume.setRange(0,100); self.volume.setValue(100)
        self.volume_value=label("Awaiting device", "status"); self.volume.sliderReleased.connect(lambda:self.device_setting(volume=self.volume.value()))
        self.muted=QCheckBox("Mute"); self.muted.clicked.connect(lambda checked:self.device_setting(muted=checked))
        self.maximum=QSpinBox(); self.maximum.setRange(0,100); self.maximum.setValue(100)
        grid.addWidget(self.volume,0,0,1,2); grid.addWidget(self.volume_value,0,2); grid.addWidget(self.muted,1,0)
        grid.addWidget(label("Volume ceiling"),1,1); grid.addWidget(self.maximum,1,2); grid.addWidget(button("APPLY CEILING",lambda:self.device_setting(maximum=self.maximum.value())),2,2)
        grid.addWidget(label("Swipe forward +5 • swipe back −5 • hold still to mute/unmute.\nLevel 100 is the maximum. Set a lower ceiling if preferred.","muted"),2,0,1,2)
        self.reverse=QCheckBox("Reverse swipe direction"); self.reverse.clicked.connect(lambda checked:self.device_setting(reverse=checked)); grid.addWidget(self.reverse,3,0,1,3)
        layout.addWidget(audio)
        light=QGroupBox("TOP STRIPS"); lights=QHBoxLayout(light)
        self.brightness=QSlider(Qt.Horizontal); self.brightness.setRange(0,60); self.brightness.setValue(18)
        self.brightness.sliderReleased.connect(lambda:self.device_setting(brightness=self.brightness.value()))
        self.brightness_value=label("Awaiting device", "status")
        self.quiet=QCheckBox("Dark when idle"); self.quiet.clicked.connect(lambda checked:self.device_setting(quiet=checked))
        lights.addWidget(self.brightness,1); lights.addWidget(self.brightness_value); lights.addWidget(self.quiet); layout.addWidget(light)
        game=QGroupBox("LED MEMORY"); play=QVBoxLayout(game)
        play.addWidget(label("Watch the sequence. Repeat it with the three zones on top.\nRed: zone 1 • green: zone 2 • blue: zone 3. Each correct round adds a step.","muted"))
        self.game_status=label("GAME OFF  /  SCORE 0  /  BEST 0","status"); play.addWidget(self.game_status)
        self.game_sound=QCheckBox("Sound cues"); self.game_sound.setChecked(True); self.game_sound.clicked.connect(lambda checked:self.device_setting(sound=checked))
        play.addWidget(row(button("PLAY MEMORY",lambda:self.control.send("game.start"),primary=True),button("STOP GAME",lambda:self.control.send("game.stop")),self.game_sound))
        play.addWidget(label("Touch the front screen to stop. During a game, top touches are game inputs; volume gestures resume afterwards.","muted")); layout.addWidget(game)
        self.hardware=label("Waiting for acknowledged device capabilities.","muted"); layout.addWidget(self.hardware); layout.addStretch()
        return page

    def diagnostics_page(self):
        page,layout=self.page("The useful details.","A bounded status journal. No credentials, conversation text, images or QR content.")
        self.timing_label=label("Provider timings appear after a voice turn.","status"); layout.addWidget(self.timing_label)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.document().setMaximumBlockCount(400); layout.addWidget(self.log,1)
        layout.addWidget(row(button("EXPORT DIAGNOSTICS",self.export_diagnostics),button("CLEAR VIEW",self.clear_diagnostics)))
        return page

    def navigate(self,index):
        self.pages.setCurrentIndex(index)
        for i,b in enumerate(self.nav): b.setChecked(i==index)

    def _load_settings(self,load_credentials):
        try:
            if self.settings_path.stat().st_size<16384:
                candidate=json.loads(self.settings_path.read_text("utf-8"))
                if isinstance(candidate,dict): self._settings=candidate
        except (OSError,ValueError): pass
        for key,widget in (("ssid",self.ssid),("timezone",self.timezone)):
            value=self._settings.get(key)
            if isinstance(value,str): widget.setText(value)
        for key,widget in (("port",self.port),("lan_host",self.lan)):
            value=self._settings.get(key)
            if isinstance(value,str) and value: widget.setCurrentText(value)
        value=self._settings.get("capture_ms",4800)
        if type(value) is int: self.capture.setValue(value)
        self.tray_check.setChecked(self._settings.get("tray") is True)
        self.remember.setChecked(self._settings.get("remember") is True and os.name=="nt")
        if load_credentials and self.remember.isChecked():
            try:
                for key,value in CredentialVault().load().items(): self.secret_fields[key].setText(value)
            except RuntimeError: self.message.setText("Saved credentials could not be loaded. Enter them for this session.")

    def connection_settings(self):
        lan=self.lan.currentText().strip()
        values={"port":self.port.currentText().strip(),"ssid":self.ssid.text(),"lan_host":"" if lan=="Auto-detect" else lan,
            "timezone":self.timezone.text().strip() or "Europe/London","capture_ms":self.capture.value()}
        values.update({key:edit.text().strip() if key!="wifi_password" else edit.text() for key,edit in self.secret_fields.items()})
        return values

    def save_preferences(self):
        values=self.connection_settings()
        safe={key:values[key] for key in ("port","ssid","lan_host","timezone","capture_ms")}
        safe.update(remember=self.remember.isChecked(),tray=self.tray_check.isChecked())
        temporary=self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(safe,indent=2)+"\n","utf-8"); temporary.replace(self.settings_path)

    def apply_timezone(self):
        if not self.control.ready or self.server_state != "stopped": return
        def applied(response):
            if response.get("ok"): self.save_preferences()
            else: self.timezone.setText(self.active_timezone)
        self.control.send("timezone", {"timezone":self.timezone.text().strip() or "Europe/London"}, applied)

    def start_server(self,checked=False,*,restart=False):
        try:
            values=self.connection_settings()
            from .desktop_worker import settings_from_control
            settings_from_control(values)
            if os.name=="nt":
                vault=CredentialVault()
                if self.remember.isChecked(): vault.save({key:values[key] for key in self.secret_fields})
                else: vault.forget()
            self.save_preferences()
            self.control.send("server_restart" if restart else "server_start",values)
        except Exception as exc:
            self.message.setText(str(exc)[:240] if type(exc) in {ValueError,RuntimeError} else "Check connection settings and credential storage.")

    def forget_credentials(self):
        try:
            if os.name=="nt": CredentialVault().forget()
            self.remember.setChecked(False)
            for edit in self.secret_fields.values(): edit.clear()
            self.save_preferences()
            self.message.setText("Saved credentials removed. A running server keeps its session credentials until stopped.")
        except Exception: self.message.setText("Windows could not remove saved credentials.")

    def scan_connections(self):
        from serial.tools import list_ports
        from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
        current=self.port.currentText(); self.port.clear()
        ports=sorted({p.device for p in list_ports.comports()}|{current or "COM4"})
        self.port.addItems(ports); self.port.setCurrentText(current or "COM4")
        current=self.lan.currentText(); self.lan.clear(); self.lan.addItem("Auto-detect","")
        addresses=sorted({a.toString() for a in QNetworkInterface.allAddresses() if a.protocol()==QAbstractSocket.IPv4Protocol and not a.isLoopback() and not a.toString().startswith("169.254.")})
        for address in addresses: self.lan.addItem(address,address)
        self.lan.setCurrentText(current)
        if not self.ssid.text():
            from .appliance import _current_wifi_ssid
            value=_current_wifi_ssid()
            if value: self.ssid.setText(value)
        self.message.setText("Connection list refreshed. Choose the PC address on the robot's Wi-Fi network.")

    def create_reminder(self):
        self.control.send("reminder_create",{"text":self.reminder_text.text(),"when":self.reminder_when.text()},self.reminder_result)

    def reminder_result(self,response):
        if not response.get("ok"):
            self.reminder_question.setText(response.get("message","Reminder was not confirmed.")); return
        result=response["result"]
        self.reminder_question.setText(result.get("message",""))
        self.answer_button.setEnabled(result.get("clarification") is True)
        self.reminder_answer.clear()
        if result.get("clarification"): self.reminder_answer.setFocus()

    @staticmethod
    def selected_id(widget):
        selected=widget.currentRow()
        if selected<0 or widget.item(selected,0) is None: return None
        return widget.item(selected,0).data(Qt.UserRole)

    def reminder_action(self,action):
        ident=self.selected_id(self.reminder_table)
        if ident is None: self.message.setText("Select a reminder first."); return
        args={"id":ident}
        if action=="reminder_snooze": args["minutes"]=self.snooze_minutes.value()
        self.control.send(action,args)

    def fill_reminders(self):
        selected=self.selected_id(self.reminder_table)
        self.reminder_table.setRowCount(len(self.reminders))
        for index,item in enumerate(self.reminders):
            local=datetime.fromtimestamp(item["due"],ZoneInfo(item["timezone"]))
            values=[str(item["id"]),"DUE" if item["state"]=="due" else item["kind"].upper(),local.strftime("%d %b %H:%M %Z"),item["text"]]
            for column,value in enumerate(values):
                cell=QTableWidgetItem(value); cell.setData(Qt.UserRole,item["id"]); cell.setToolTip(value)
                if item["state"]=="due": cell.setForeground(QColor("#ffd58c"))
                self.reminder_table.setItem(index,column,cell)
            if selected==item["id"]: self.reminder_table.selectRow(index)

    def fill_projects(self):
        for combo in (self.project_select,self.vision_project):
            ident=combo.currentData(); combo.blockSignals(True); combo.clear()
            for project in self.projects: combo.addItem(project["name"],project["id"])
            restored=combo.findData(ident)
            if restored>=0: combo.setCurrentIndex(restored)
            combo.blockSignals(False)
        self.load_entries()

    def load_entries(self,*args):
        ident=self.project_select.currentData()
        if ident is None: self.entry_table.setRowCount(0); return
        self.control.send("entry_list",{"project_id":ident,"query":self.search.text()},self.entries_result)

    def entries_result(self,response):
        if not response.get("ok"): return
        self.entries=response["result"]; selected=self.selected_id(self.entry_table)
        self.entry_table.setRowCount(len(self.entries))
        for index,item in enumerate(self.entries):
            values=[str(item["id"]),item["kind"].upper(),"DONE" if item["done"] else "NEXT" if item["kind"]=="step" else "",item["text"]]
            for column,value in enumerate(values):
                cell=QTableWidgetItem(value); cell.setData(Qt.UserRole,item["id"]); cell.setToolTip(value); self.entry_table.setItem(index,column,cell)
            if selected==item["id"]: self.entry_table.selectRow(index)

    def add_entry(self,kind):
        project=self.project_select.currentData()
        if project is None: self.message.setText("Create or select a project first."); return
        def result(response):
            if response.get("ok"): self.entry_text.clear(); self.load_entries()
        self.control.send("entry_add",{"project_id":project,"kind":kind,"text":self.entry_text.text()},result)

    def complete_entry(self):
        ident=self.selected_id(self.entry_table)
        if ident is None: self.message.setText("Select a checklist step first."); return
        self.control.send("entry_done",{"id":ident,"done":True},lambda _:self.load_entries())

    def delete_entry(self):
        ident=self.selected_id(self.entry_table)
        if ident is None: return
        if QMessageBox.question(self,"Delete record",f"Delete project record {ident}?")==QMessageBox.Yes:
            self.control.send("entry_delete",{"id":ident},lambda _:self.load_entries())

    def calc_changed(self,index):
        self.calc_from.setEnabled(index==1); self.calc_to.setEnabled(index==1)
        hints=["Arithmetic: + − * / % ** and parentheses.","Enter a number, then choose compatible source and destination units.","Supply two values: V=5, R=1000  /  V=12, I=0.25. Units are volts, amperes and ohms.","Enter four or five colours in reading order: yellow, violet, red, gold."]
        self.calc_hint.setText(hints[index]); self.calc_input.clear()
        self.calc_input.setPlaceholderText(["(12 + 3) * 4","25.4","V=5, R=1000","yellow, violet, red, gold"][index])

    def calculate(self):
        index=self.calc_mode.currentIndex(); text=self.calc_input.text()
        try:
            if index==0: action,args="local_tool",{"name":"calculate","arguments":{"expression":text}}
            elif index==1: action,args="convert",{"value":float(text),"source":self.calc_from.currentText(),"target":self.calc_to.currentText()}
            elif index==2:
                values={}
                for part in text.split(","):
                    key,value=part.split("="); name={"v":"voltage","i":"current","r":"resistance"}[key.strip().lower()]
                    if name in values: raise ValueError()
                    values[name]=float(value)
                action,args="ohms",values
            else: action,args="resistor",{"bands":[x.strip() for x in text.split(",")]}
            self.control.send(action,args,self.calculation_result)
        except (ValueError,KeyError): self.calc_result.setText("Check the input format shown above.")

    def calculation_result(self,response):
        if not response.get("ok"): self.calc_result.setText(response.get("message","Calculation failed.")); return
        result=response["result"]
        if "tool" in result:
            if not result["ok"]: self.calc_result.setText(result["error"]["message"]); return
            result=result["data"]
        self.calc_result.setText(result.get("spoken",str(result.get("result","No result"))))

    def device_setting(self,**values):
        self.control.send("device.settings",values)

    def on_event(self,name,data):
        if name=="ready":
            self.message.setText("Local utilities ready. Connect Kadence when you're ready.")
            self.apply_timezone()
            self.update_controls()
        elif name=="server":
            self.server_state=data.get("state","stopped")
            self.server_label.setText("SERVER  "+self.server_state.upper())
            if self.server_state=="running": self.started_at=time.monotonic()
            if self.server_state=="stopped": self.started_at=None; self.robot_connected=False; self.robot_label.setText("ROBOT  DISCONNECTED")
            self.update_controls()
        elif name=="robot":
            self.robot_connected=data.get("connected") is True
            self.robot_label.setText("ROBOT  "+("CONNECTED" if self.robot_connected else "DISCONNECTED"))
        elif name=="activity":
            state=data.get("state","idle"); self.avatar.phase=state; self.activity.setText(state.upper().replace("-"," "))
        elif name=="turn": self.turn_info.setText(f"Completed turns  {data.get('completed',0)}")
        elif name=="utilities":
            self.active_timezone=data.get("clock",{}).get("timezone",self.active_timezone)
            self.reminders=data.get("reminders",[]); self.projects=data.get("projects",[])
            self.fill_reminders(); self.fill_projects(); self.tick()
        elif name=="reminders_due":
            count=data.get("count",1)
            self.message.setText(f"{count} reminder(s) due. Open Reminders to dismiss or snooze.")
            if hasattr(self,"tray") and self.tray.isVisible(): self.tray.showMessage("Kadence",f"{count} reminder(s) due. Open Kadence to review.",QSystemTrayIcon.Information,6000)
            QApplication.beep()
        elif name=="device":
            if not self.volume.isSliderDown(): self.volume.setValue(data.get("volume",100))
            if not self.brightness.isSliderDown(): self.brightness.setValue(data.get("brightness",18))
            self.volume_value.setText(f"{data.get('volume',100)} / 100")
            self.brightness_value.setText(f"{data.get('brightness',18)} / 60")
            for widget,key in ((self.muted,"muted"),(self.quiet,"quiet"),(self.reverse,"reverse"),(self.game_sound,"sound")): widget.setChecked(data.get(key) is True)
            if not self.maximum.hasFocus(): self.maximum.setValue(data.get("maximum",100))
            self.game_status.setText(f"{data.get('game','off').upper()}  /  SCORE {data.get('score',0)}  /  BEST {data.get('best',0)}")
            self.hardware.setText(f"Strips: {'ready' if data.get('leds') else 'unavailable'}  •  Top touch: {'ready' if data.get('top_touch') else 'unavailable'}  •  Camera: {'active' if data.get('camera_active') else 'off'}")
            self.avatar.phase=data.get("presentation","idle")
            self.activity.setText(self.avatar.phase.upper().replace("-"," "))
        elif name=="snapshot":
            encoded=data.get("png","")
            if encoded:
                pixmap=QPixmap(); pixmap.loadFromData(base64.b64decode(encoded,validate=True),"PNG"); self.snapshot_pixmap=pixmap
                self.preview.setPixmap(pixmap.scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            else: self.snapshot_pixmap=None; self.preview.setPixmap(QPixmap()); self.preview.setText("CAMERA OFF\n\nCapture a snapshot to begin.")
            values=[data.get("description","")]
            values.extend("QR (local, text only): "+str(qr) for qr in data.get("qr",[]))
            self.vision_result.setPlainText("\n\n".join(x for x in values if x))
        elif name=="result":
            if not data.get("ok"): self.message.setText(data.get("message","Operation was not confirmed."))
            elif isinstance(data.get("result"),dict) and data["result"].get("message"): self.message.setText(data["result"]["message"])
        elif name=="timing":
            if data.get("stage") in {"stt","reasoning","tts"}:
                self.timings[data["stage"]]=data.get("elapsed_ms",0)
                self.timing_label.setText("  /  ".join(f"{key.upper()} {value/1000:.2f}s" for key,value in self.timings.items()))
        elif name in {"fatal","message"}:
            self.message.setText(data.get("message","Local services unavailable."))
            if name=="fatal": self.update_controls()
        self.record_diagnostic(name,data)

    def update_controls(self):
        ready=self.control.ready and not self.quitting
        self.start_button.setEnabled(ready and self.server_state=="stopped")
        self.stop_button.setEnabled(ready and self.server_state in {"running","starting"})
        self.restart_button.setEnabled(ready and self.server_state=="running")
        self.timezone.setEnabled(ready and self.server_state=="stopped")

    def tick(self):
        try: now=datetime.now(ZoneInfo(self.active_timezone))
        except Exception: now=datetime.now(timezone.utc)
        self.clock.setText(now.strftime("%a %d %b %Y  %H:%M:%S %Z").upper())
        if self.started_at:
            seconds=int(time.monotonic()-self.started_at)
            self.runtime_info.setText(f"Uptime {seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}\n"+("Robot connected." if self.robot_connected else "Waiting for the robot. Local utilities are ready."))
        else: self.runtime_info.setText("Server stopped. Local reminders work while this app is open.")
        due=[r for r in self.reminders if r["state"]=="due"]
        scheduled=[r for r in self.reminders if r["state"]=="scheduled"]
        if due: self.next_due.setText(f"{len(due)} REMINDER(S) DUE\n"+due[0]["text"][:100])
        elif scheduled:
            item=min(scheduled,key=lambda r:r["due"]); seconds=max(0,int(item["due"]-time.time()))
            self.next_due.setText(f"NEXT IN {seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}\n"+item["text"][:100])
        else: self.next_due.setText("No scheduled reminders.")

    def record_diagnostic(self,name,data):
        allowed={"server","robot","activity","turn","device","device_status","alert","reminders_due","storage","integration","timing"}
        if name not in allowed: return
        safe={}
        states={"stopped","starting","running","stopping","idle","listening","thinking","speaking","tool-working","camera","alert","unavailable","configuration_required","delivered","review_in_windows","offline","degraded","fault","recovery","booting","attentive"}
        for key in ("state","connected","completed","count","free_heap","free_psram","elapsed_ms","stage"):
            value=data.get(key)
            if type(value) in {int,float,bool}: safe[key]=value
            elif isinstance(value,str) and (value in states or key=="stage" and value in {"stt","reasoning","tts"}): safe[key]=value
        record={"at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"event":name,**safe}
        self.diagnostic.append(record)
        self.log.appendPlainText(record["at"][11:19]+"  "+name.upper()+"  "+" ".join(f"{k}={v}" for k,v in safe.items()))

    def export_diagnostics(self):
        filename,_=QFileDialog.getSaveFileName(self,"Export diagnostics","Kadence-diagnostics.json","JSON (*.json)")
        if filename:
            Path(filename).write_text(json.dumps({"format":"kadence-diagnostics-v1","build":build_info(),"events":list(self.diagnostic)},indent=2)+"\n","utf-8")
            self.message.setText("Sanitised diagnostic report exported.")

    def clear_diagnostics(self): self.diagnostic.clear(); self.log.clear()

    def _make_tray(self):
        pixmap=QPixmap(64,64); pixmap.fill(QColor("#050706")); painter=QPainter(pixmap)
        painter.setPen(QColor("#b4ff8d")); painter.setFont(QFont("Consolas",38,QFont.Bold)); painter.drawText(pixmap.rect(),Qt.AlignCenter,"K"); painter.end()
        icon=QIcon(pixmap); self.setWindowIcon(icon)
        self.tray=QSystemTrayIcon(icon,self); self.tray.setToolTip("Kadence • Control")
        menu=QMenu(); menu.addAction("Open Kadence",self.show_window); menu.addAction("Quit",self.quit_app); self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.show_window() if reason in {QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick} else None)
        self.tray.messageClicked.connect(lambda:(self.show_window(),self.navigate(1)))
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
        else: self.tray_check.setChecked(False); self.tray_check.setEnabled(False)

    def show_window(self): self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self,event):
        if self.quitting: event.accept(); return
        if self.tray_check.isChecked() and self.tray.isVisible(): self.save_preferences(); self.hide(); event.ignore(); return
        event.ignore(); self.quit_app()

    def quit_app(self):
        if self.quitting: return
        self.quitting=True; self.save_preferences(); self.update_controls()
        self.message.setText("Stopping Kadence and releasing the robot…")
        self.control.shutdown()

    def _worker_exited(self):
        if self.quitting: self.tray.hide(); QApplication.instance().quit()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.snapshot_pixmap is not None: self.preview.setPixmap(self.snapshot_pixmap.scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
