"""Render each actual Qt page with synthetic data for release inspection."""
import argparse
from pathlib import Path
import tempfile
from datetime import datetime,timezone
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from kcore.desktop_ui import MainWindow

class PreviewControl(QObject):
    event=Signal(str,dict); exited=Signal()
    ready=True
    def send(self,action,args=None,callback=None,**kwargs):
        if action=='entry_list' and callback:
            callback({'ok':True,'result':[
                {'id':1,'kind':'step','done':1,'text':'Confirm sensor supply voltage'},
                {'id':2,'kind':'step','done':0,'text':'Measure idle current and record the reading'},
                {'id':3,'kind':'note','done':0,'text':'Use the labelled breakout on the left of the bench.'}]})
    def shutdown(self): self.exited.emit()


def render(output):
    output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        window=MainWindow(control=PreviewControl(),directory=Path(tmp),load_credentials=False)
        window.on_event('utilities',{'clock':{'timezone':'Europe/London'},
            'projects':[{'id':1,'name':'Sensor bench'}],
            'reminders':[{'id':1,'due':datetime.now(timezone.utc).timestamp()+1200,'timezone':'Europe/London','state':'scheduled','kind':'reminder','text':'Check the print'},
                         {'id':2,'due':datetime.now(timezone.utc).timestamp()-60,'timezone':'Europe/London','state':'due','kind':'focus','text':'Focus session finished. Time for a break.'}]})
        window.on_event('device',{'ok':True,'volume':55,'maximum':80,'brightness':18,'leds':True,'top_touch':True,'presentation':'thinking','game':'off','score':0,'best':7})
        window.on_event('timing',{'stage':'stt','elapsed_ms':980})
        window.on_event('timing',{'stage':'reasoning','elapsed_ms':1350})
        window.on_event('timing',{'stage':'tts','elapsed_ms':940})
        window.show()
        for width,height in [(1160,800),(980,690)]:
            window.resize(width,height)
            for index,name in enumerate(['overview','reminders','workbench','vision','device','diagnostics']):
                window.navigate(index)
                for _ in range(4): app.processEvents()
                assert window.grab().save(str(output/f'{name}-{width}.png'))
        window.tray.hide(); window.hide(); window.deleteLater(); app.processEvents()
    print('DESKTOP_RENDER PASS pages=6 sizes=2 synthetic_data=1')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output',type=Path); args=parser.parse_args(); render(args.output)
