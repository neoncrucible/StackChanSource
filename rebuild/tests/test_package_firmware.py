import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location("package_firmware",Path(__file__).resolve().parents[1]/"tools"/"package_firmware.py")
pack=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.build=self.base/"build"
        self.build.mkdir()
        self.manifest={"extra_esptool_args":{"chip":"esp32s3"},
                       "flash_settings":{"flash_mode":"dio","flash_size":"16MB","flash_freq":"80m"},
                       "write_flash_args":["--flash_mode","dio","--flash_size","16MB","--flash_freq","80m"],
                       "flash_files":{"0x0":"bootloader/bootloader.bin","0x8000":"partition_table/partition-table.bin","0x10000":"app.bin"}}
        for relative in self.manifest["flash_files"].values():
            file=self.build/relative
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(b"example firmware\0")

    def tearDown(self): self.temp.cleanup()

    def package(self):
        (self.build/"flasher_args.json").write_text(json.dumps(self.manifest))
        return pack.package(self.build,self.base/"release",source_commit="a"*40)

    def test_paths_hashes_and_source_are_preserved(self):
        archive=self.package()
        with zipfile.ZipFile(archive) as z:
            self.assertIn("bootloader/bootloader.bin",z.namelist())
            release=json.loads(z.read("RELEASE.json"))
            self.assertEqual(release["source_commit"],"a"*40)
            for line in z.read("SHA256SUMS").decode().splitlines():
                digest,path=line.split("  ",1)
                self.assertEqual(hashlib.sha256(z.read(path)).hexdigest(),digest)

    def test_ci_cli_uses_runner_commit_without_git_access(self):
        (self.build/"flasher_args.json").write_text(json.dumps(self.manifest))
        result=subprocess.run(
            [sys.executable,pack.__file__,"--build",str(self.build),
             "--output",str(self.base/"ci-release"),"--source-commit","b"*40],
            env={**os.environ,"GIT_DIR":str(self.base/"unavailable-git")},
            text=True,capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        with zipfile.ZipFile(self.base/"ci-release.zip") as z:
            self.assertEqual(json.loads(z.read("RELEASE.json"))["source_commit"],"b"*40)

    def test_stack_report_must_match_the_packaged_binary(self):
        report={"format":1,"binary_sha256":hashlib.sha256((self.build/"app.bin").read_bytes()).hexdigest()}
        (self.build/"boot_stack_report.json").write_text(json.dumps(report))
        with zipfile.ZipFile(self.package()) as z:
            self.assertEqual(json.loads(z.read("boot_stack_report.json")),report)
        (self.build/"app.bin").write_bytes(b"different firmware")
        with self.assertRaisesRegex(ValueError,"different firmware image"):
            self.package()

    def test_calibration_offset_and_bad_flash_settings_are_rejected(self):
        self.manifest["flash_files"]["0x9000"]="app.bin"
        with self.assertRaises(ValueError): self.package()
        self.manifest["flash_files"].pop("0x9000")
        self.manifest["write_flash_args"].append("--erase-all")
        with self.assertRaises(ValueError): self.package()

    def test_oversize_and_path_escape_are_rejected(self):
        file=self.build/"bootloader"/"bootloader.bin"
        file.write_bytes(b"x"*0x8001)
        with self.assertRaises(ValueError): self.package()
        file.write_bytes(b"ok")
        for path in ["../outside.bin","..\\outside.bin","C:\\outside.bin"]:
            self.manifest["flash_files"]["0x10000"]=path
            with self.subTest(path=path),self.assertRaises(ValueError): self.package()


if __name__=="__main__": unittest.main()
