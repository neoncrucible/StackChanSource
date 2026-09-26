from __future__ import annotations
import sys


def main():
    if "--unitv2-setup" in sys.argv:
        from .unitv2_setup import main as setup
        index = sys.argv.index("--unitv2-setup")
        try: return setup(sys.argv[index+1] if index+1 < len(sys.argv) else "192.168.40.175")
        except Exception as exc:
            print("UnitV2 setup failed: "+str(exc))
            input("Press Enter to close. ")
            return 1
    if "--speech-decode-check" in sys.argv:
        from .speech_stream import decoder_check
        import json
        from pathlib import Path
        index = sys.argv.index("--speech-decode-check")
        if index + 1 >= len(sys.argv): return 2
        print(json.dumps(decoder_check(Path(sys.argv[index + 1]).read_bytes())))
        return 0
    if "--vision-response-check" in sys.argv:
        # Packaging contract check: no camera access, key or network request.
        import json
        from pathlib import Path
        from .vision_provider import description_text
        index = sys.argv.index("--vision-response-check")
        if index + 1 >= len(sys.argv): return 2
        raw = Path(sys.argv[index + 1]).read_bytes()
        if len(raw) > 128 * 1024: return 2
        text = description_text(json.loads(raw))
        print(json.dumps({"parsed":True,"chars":len(text)}))
        return 0
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
