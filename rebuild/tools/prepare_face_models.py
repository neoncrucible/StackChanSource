"""Build-time, pinned OpenCV Zoo model download. Runtime never downloads models."""
import argparse
import hashlib
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kcore.local_faces import MODELS, ZOO_COMMIT


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (folder, size, digest) in MODELS.items():
        path = directory / name
        if path.exists() and path.stat().st_size == size and hashlib.sha256(path.read_bytes()).hexdigest() == digest: continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{ZOO_COMMIT}/models/{folder}/{name}"
        temporary = path.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
                total = 0
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    if total > size: raise ValueError("Model exceeds pinned size")
                    output.write(chunk)
            if total != size or hashlib.sha256(temporary.read_bytes()).hexdigest() != digest: raise ValueError("Model hash verification failed")
            temporary.replace(path)
        finally: temporary.unlink(missing_ok=True)
        print("FACE_MODEL VERIFIED", name)
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    prepare(parser.parse_args().directory)
