"""Install/update integrity and shortcuts in temporary directories only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package_desktop',ROOT/'tools'/'package_desktop.py')
packager=importlib.util.module_from_spec(spec); spec.loader.exec_module(packager)


class Package(unittest.TestCase):
    def bundle(self, root, commit):
        app=root/('app-'+commit[:12]); app.mkdir()
        (app/'Kadence.exe').write_bytes(b'fixture-executable-not-for-launch')
        (app/'_internal').mkdir(); (app/'_internal'/'fixture.dll').write_bytes(b'library')
        output=root/('package-'+commit[:12])
        archive=packager.host_package(app,commit,output)
        return output,archive

    def test_host_archive_complete_and_no_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            output,archive=self.bundle(Path(tmp),'a'*40)
            with zipfile.ZipFile(archive) as z:
                self.assertIn('Install-Kadence.cmd',z.namelist())
                self.assertIn('_internal/fixture.dll',z.namelist())
                self.assertFalse(any(name.startswith('Firmware/') for name in z.namelist()))
                for line in z.read('SHA256SUMS').decode().splitlines():
                    digest,name=line.split('  ',1)
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
            self.assertFalse(json.loads((output/'RELEASE.json').read_text())['firmware_included'])

    @unittest.skipUnless(os.name=='nt','Windows installer and shortcut integration')
    def test_install_update_and_corrupt_package_preserve_previous_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); install=root/'installed'; desktop=root/'desktop'
            # User data is separate and must remain byte-for-byte untouched.
            data=root/'Kadence'; data.mkdir(); marker=data/'desktop-settings.json'
            marker.write_text('{"ollama_model":"custom:latest"}')
            def run(bundle):
                return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(bundle/'install_desktop.ps1'),'-InstallRoot',str(install),
                    '-DesktopDirectory',str(desktop),'-NoLaunch'],capture_output=True,text=True,timeout=60)
            first,_=self.bundle(root,'a'*40)
            result=run(first); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            shortcut=(desktop/'Kadence.lnk').read_bytes()
            second,_=self.bundle(root,'b'*40)
            (second/'_internal'/'fixture.dll').write_bytes(b'corrupted')
            self.assertNotEqual(run(second).returncode,0)
            self.assertEqual((desktop/'Kadence.lnk').read_bytes(),shortcut)
            self.assertFalse(any((install/'versions').glob('*bbbbbbbbbbbb')))
            (second/'_internal'/'fixture.dll').write_bytes(b'library')
            result=run(second); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotEqual((desktop/'Kadence.lnk').read_bytes(),shortcut)
            self.assertEqual(len(list((install/'versions').iterdir())),2)
            result=run(second); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(marker.read_text(),'{"ollama_model":"custom:latest"}')
