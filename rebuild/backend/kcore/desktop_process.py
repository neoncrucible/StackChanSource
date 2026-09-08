"""Qt supervisor for one private host process; no serial or provider authority."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class ControlProcess(QObject):
    event = Signal(str, dict)
    exited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.ready = False
        self.buffer = bytearray()
        self.pending = {}
        self.sequence = 0
        self._closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._expire)
        self.timer.start()

    def start(self):
        if self.process.state() != QProcess.NotRunning: return
        self.process.setProgram(sys.executable)
        self.process.setArguments(["--worker"] if getattr(sys, "frozen", False) else ["-m", "kcore.desktop_worker"])
        self.process.start()

    def _error(self, error):
        self.ready = False
        self.event.emit("fatal", {"message": "The local service could not run. Restart Kadence."})
        if self.process.state() == QProcess.NotRunning: self.exited.emit()

    def send(self, action, args=None, callback=None, timeout=110):
        if not self.ready or self.process.state() != QProcess.Running:
            self.event.emit("message", {"message": "Local services are not ready."}); return None
        if len(self.pending)>=8:
            self.event.emit("message", {"message": "Wait for an active operation to finish."}); return None
        self.sequence += 1
        ident = self.sequence
        raw = json.dumps({"v": 1, "id": ident, "action": action, "args": args or {}}, ensure_ascii=True, allow_nan=False).encode("ascii")+b"\n"
        if len(raw)>32768: raise ValueError("Control request exceeds the size limit")
        self.pending[ident] = (callback, time.monotonic()+timeout)
        if self.process.write(raw) != len(raw):
            self.pending.pop(ident, None)
            self.event.emit("message", {"message": "Control request could not be sent."})
        return ident

    def _read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self.buffer:
            raw, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            if len(raw)>1024*1024: self.process.kill(); return
            try:
                message = json.loads(raw)
                if message.get("v") != 1 or not isinstance(message.get("event"),str) or not isinstance(message.get("data"),dict): raise ValueError()
            except (ValueError, AttributeError, RecursionError):
                self.process.kill(); return
            name, data = message["event"], message["data"]
            if name == "ready": self.ready = True
            if name == "result":
                callback, _ = self.pending.pop(data.get("id"), (None, None))
                if callback: callback(data)
            self.event.emit(name, data)
        if len(self.buffer)>1024*1024: self.process.kill()

    def _expire(self):
        for ident, (callback, deadline) in list(self.pending.items()):
            if time.monotonic()>deadline:
                del self.pending[ident]
                response = {"id": ident, "ok":False, "message":"The outcome was not confirmed. Refresh before trying again."}
                if callback: callback(response)
                self.event.emit("result", response)

    def _finished(self, code, status):
        self.ready = False
        for ident, (callback, _) in list(self.pending.items()):
            if callback: callback({"id":ident,"ok":False,"message":"Local service stopped; outcome not confirmed."})
        self.pending.clear()
        self.event.emit("server", {"state":"stopped"})
        if not self._closing: self.event.emit("fatal", {"message":"Local services stopped. Reopen Kadence to reconnect."})
        self.exited.emit()

    def shutdown(self):
        if self._closing: return
        self._closing = True
        if self.process.state() == QProcess.NotRunning: self.exited.emit(); return
        if self.ready: self.send("quit")
        else: self.process.closeWriteChannel()
        QTimer.singleShot(12000, self._force_stop)

    def _force_stop(self):
        if self.process.state() != QProcess.NotRunning:
            self.event.emit("message", {"message":"Shutdown timed out. Device state could not be confirmed; reset the robot before restarting."})
            self.process.kill()
