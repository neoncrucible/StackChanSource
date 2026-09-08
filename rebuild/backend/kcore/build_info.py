"""Non-secret identity embedded by the Windows package builder."""
import json
from pathlib import Path
import sys


def build_info():
    if getattr(sys,'frozen',False):
        value=json.loads((Path(sys._MEIPASS)/'BUILD.json').read_text())
        return {key:value[key] for key in ('source_commit','host_version')}
    return {'source_commit':'source checkout','host_version':'0.3.2'}
