"""Local CPU face evidence. No cloud identity calls; explicit enrollment only."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import struct
import sys
import threading

ZOO_COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODELS = {
    "face_detection_yunet_2023mar.onnx": ("face_detection_yunet", 232589, "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": ("face_recognition_sface", 38696353, "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
FINGERPRINT = "sface:" + MODELS["face_recognition_sface_2021dec.onnx"][2]
PREPROCESSING = "yunet-2023mar;alignCrop-112x112;BGR;float32-l2;v1"


def normalize(values):
    values = tuple(float(x) for x in values)
    if len(values) != 128 or not all(math.isfinite(x) for x in values): raise ValueError("Invalid face embedding.")
    length = math.sqrt(sum(x*x for x in values))
    if not math.isfinite(length) or length < 1e-8: raise ValueError("Invalid face embedding.")
    return tuple(x/length for x in values)


def encode(values): return struct.pack("<128f", *normalize(values))
def decode(blob):
    if len(blob) != 512: raise ValueError("Incompatible face profile.")
    return normalize(struct.unpack("<128f", blob))
def similarity(a, b): return sum(x*y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True)
class Face:
    box: tuple[float, float, float, float]
    embedding: tuple[float, ...]
    quality: float


def match(embedding, profiles, *, threshold=.55, margin=.08):
    """Per-person best score; several samples of one person aren't runner-up identities."""
    scores = {}
    for person, vector in profiles:
        score = similarity(embedding, vector)
        scores[person] = max(scores.get(person, -1), score)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] < threshold: return None, "unresolved"
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin: return None, "ambiguous"
    return ranked[0][0], "candidate"


class LocalFaces:
    def __init__(self, root, progress=None):
        self.progress = progress or (lambda stage: None)
        bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "face_models"
        self.directory = bundled if all((bundled / n).exists() for n in MODELS) else Path(root) / "models" / "faces"
        self._lock = threading.Lock()
        self._detector = self._recognizer = None
        self.health = "not_loaded"

    def load(self):
        self.progress("import_cv2")
        import cv2
        self.progress("verify_models")
        for name, (_, size, digest) in MODELS.items():
            path = self.directory / name
            if not path.exists():
                self.health = "models_missing"
                raise RuntimeError("Local face models are missing. Install the complete desktop package.")
            if path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                self.health = "models_invalid"
                raise RuntimeError("Local face model verification failed.")
        self.progress("load_detector")
        self._detector = cv2.FaceDetectorYN.create(str(self.directory / next(iter(MODELS))), "", (320, 240), .9, .3, 100)
        self.progress("load_recognizer")
        self._recognizer = cv2.FaceRecognizerSF.create(str(self.directory / "face_recognition_sface_2021dec.onnx"), "")
        self.health = "ready"

    def analyze(self, png):
        self.progress("import_cv2")
        import cv2
        import numpy as np
        with self._lock:
            if self._detector is None: self.load()
            image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.shape[0] > 480 or image.shape[1] > 640: raise ValueError("Invalid perception frame.")
            self._detector.setInputSize((image.shape[1], image.shape[0]))
            self.progress("detect")
            _, detections = self._detector.detect(image)
            self.progress("detected")
            faces = []
            for detection in (() if detections is None else detections[:8]):
                x, y, w, h = (float(v) for v in detection[:4])
                if min(w, h) < 40: continue
                crop = self._recognizer.alignCrop(image, detection)
                # Reject severe blur rather than producing misleading identity evidence.
                if cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() < 20: continue
                vector = normalize(self._recognizer.feature(crop).reshape(-1))
                faces.append(Face((x/image.shape[1], y/image.shape[0], w/image.shape[1], h/image.shape[0]), vector, float(detection[-1])))
            return tuple(faces)
