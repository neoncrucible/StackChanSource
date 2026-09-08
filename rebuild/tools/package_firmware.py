"""Package the actual IDF flash manifest, preserving paths and calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
ALLOWED_OFFSETS={0x0,0x8000,0xd000,0x10000}


def package(build: Path, output: Path, *, source_commit: str | None = None) -> Path:
    manifest=json.loads((build / "flasher_args.json").read_text())
    if manifest.get("extra_esptool_args",{}).get("chip") != "esp32s3":
        raise ValueError("flash manifest target is not ESP32-S3")
    settings=manifest.get("flash_settings",{})
    if settings.get("flash_size") != "16MB" or settings.get("flash_mode") not in {"dio","qio"} or settings.get("flash_freq") != "80m":
        raise ValueError("unexpected flash geometry or boot settings")
    expected_args={"--flash_mode":settings["flash_mode"],"--flash_size":"16MB","--flash_freq":"80m"}
    args=manifest.get("write_flash_args",[])
    if len(args)!=6 or dict(zip(args[::2],args[1::2]))!=expected_args:
        raise ValueError("unexpected esptool write arguments")
    files=manifest["flash_files"]
    offsets={int(offset,0) for offset in files}
    if not {0,0x8000,0x10000}.issubset(offsets) or not offsets.issubset(ALLOWED_OFFSETS):
        raise ValueError("unexpected flash offsets; calibration/storage protection refused package")
    output.mkdir(parents=True,exist_ok=True)
    source_commit=source_commit or subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("full source commit required")
    entries={}
    for offset,relative in files.items():
        if not isinstance(relative,str) or "\\" in relative or ":" in relative:
            raise ValueError("flash paths must be portable relative POSIX paths")
        relative_path=Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("unsafe flash manifest path")
        source=(build / relative_path).resolve()
        if not source.is_relative_to(build.resolve()) or not source.is_file():
            raise ValueError("flash manifest references a missing or external file")
        size=source.stat().st_size
        address=int(offset,0)
        limits={0:0x8000,0x8000:0x1000,0xd000:0x2000,0x10000:0x400000}
        if not 0<size<=limits[address]:
            raise ValueError("flash file exceeds its allowed region")
        target=output / relative_path
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        entries[relative_path.as_posix()]={"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"bytes":size,"offset":offset}
    shutil.copyfile(build / "flasher_args.json",output / "flasher_args.json")
    stack_report = build / "boot_stack_report.json"
    if stack_report.is_file():
        report = json.loads(stack_report.read_text())
        app_path = next(relative for offset, relative in files.items() if int(offset, 0) == 0x10000)
        if report.get("binary_sha256") != entries[app_path]["sha256"]:
            raise ValueError("startup stack report belongs to a different firmware image")
        shutil.copyfile(stack_report, output / stack_report.name)
    shutil.copyfile(ROOT / "rebuild" / "tools" / "flash_bundle.ps1",output / "flash.ps1")
    release={"format":1,"candidate":"Kadence RC2","source_commit":source_commit,"branch":"kadence/rebuild-kade",
             "idf":"5.5.4","chip":"esp32s3","flash_size":"16MB","files":entries,"physical_signoff":False}
    (output / "RELEASE.json").write_text(json.dumps(release,indent=2)+"\n")
    sums=[]
    for file in sorted(output.rglob("*")):
        if file.is_file() and file.name!="SHA256SUMS":
            sums.append(hashlib.sha256(file.read_bytes()).hexdigest()+"  "+file.relative_to(output).as_posix())
    (output / "SHA256SUMS").write_text("\n".join(sums)+"\n")
    archive=output.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for file in sorted(output.rglob("*")):
            if file.is_file(): z.write(file,file.relative_to(output))
    return archive


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--build",type=Path,default=ROOT / "rebuild" / "firmware" / "build")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--source-commit",help="Full checkout SHA supplied by the CI runner; defaults to local HEAD")
    args=parser.parse_args()
    commit=args.source_commit or subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    output=args.output or ROOT / "rebuild" / "dist" / ("Kadence-RC2-Firmware-"+commit[:12])
    archive=package(args.build,output,source_commit=commit)
    print(f"KADENCE_PACKAGE PASS file={archive.name} offsets=verified calibration=preserved hashes=1")
