from __future__ import annotations
import sys


def main():
    if "--speech-child" in sys.argv:
        from .speech_child import main as speech_child
        return speech_child()
    if "--build-info" in sys.argv:
        from .build_info import build_info
        import json
        print(json.dumps(build_info()))
        return 0
    if "--worker" in sys.argv:
        from .desktop_worker import main as worker
        return worker()
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .context_store import default_data_dir
    from .desktop_ui import MainWindow
    app=QApplication(sys.argv)
    app.setApplicationName("Kadence")
    app.setOrganizationName("Kadence")
    app.setQuitOnLastWindowClosed(False)
    directory=default_data_dir(); directory.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(directory/"desktop.lock")); lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None,"Kadence is running","Kadence is already open. Use its taskbar or tray icon.")
        return 0
    window=MainWindow(directory=directory)
    window.show()
    QTimer.singleShot(0,window.control.start)
    result=app.exec()
    lock.unlock()
    return result


if __name__=="__main__": raise SystemExit(main())
