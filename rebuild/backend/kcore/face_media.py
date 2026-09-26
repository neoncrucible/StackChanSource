"""Explicit local enrollment references. Automatic perception never calls this."""
from __future__ import annotations
import base64
import hashlib
import io
import math
from pathlib import Path
import re
import time
import uuid

from PIL import Image, ImageDraw

# Three base64 photos plus metadata must fit the 1 MiB desktop wire limit.
MAX_PHOTO_BYTES = 200 * 1024
PURPOSE = "face_enrollment_reference"


def _image(png):
    if len(png) > 1024 * 1024: raise ValueError("Face preview exceeds its size limit.")
    image = Image.open(io.BytesIO(png))
    if image.width > 640 or image.height > 480: raise ValueError("Invalid face preview dimensions.")
    return image.convert("RGB")


def _png(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def preview(png, faces):
    image = _image(png)
    draw = ImageDraw.Draw(image)
    for face in faces:
        x,y,w,h = face.box
        draw.rectangle((int(x*image.width),int(y*image.height),int((x+w)*image.width),int((y+h)*image.height)),outline="#6afa8e",width=2)
    image.thumbnail((400,300))
    return base64.b64encode(_png(image)).decode("ascii")


def reference(frame, face):
    image = _image(frame.png)
    x,y,w,h = face.box
    if not all(math.isfinite(v) for v in face.box) or w <= 0 or h <= 0:
        raise ValueError("Invalid face crop.")
    box = (max(0,int((x-w*.15)*image.width)),max(0,int((y-h*.15)*image.height)),
           min(image.width,int((x+w*1.15)*image.width)),min(image.height,int((y+h*1.15)*image.height)))
    if box[2] <= box[0] or box[3] <= box[1]: raise ValueError("Face is outside the image.")
    image = image.crop(box)
    image.thumbnail((256,256))
    return {"png":_png(image),"source":frame.source,"captured":frame.captured_at}


class ProfilePhotos:
    def __init__(self, database):
        self.root = Path(database).parent.parent
        self.directory = self.root / "media" / "face-profiles"

    def path(self, value):
        if not isinstance(value,str) or not re.fullmatch(r"media/face-profiles/[0-9a-f]{32}\.png",value):
            raise ValueError("Invalid profile photo path.")
        target = self.root / value
        if target.is_symlink() or target.resolve().parent != self.directory.resolve() or self.directory.is_symlink():
            raise ValueError("Invalid profile photo location.")
        return target

    def add(self, db, items, staged):
        if items is None: return [None]*3
        if len(items) != 3: raise ValueError("Three review photos are required.")
        self.directory.mkdir(parents=True,exist_ok=True)
        ids = []
        for item in items:
            png = item["png"]
            if not isinstance(png,bytes) or not 1 <= len(png) <= MAX_PHOTO_BYTES: raise ValueError("Invalid profile photo size.")
            image = Image.open(io.BytesIO(png))
            if image.format != "PNG" or not 1 <= image.width <= 256 or not 1 <= image.height <= 256: raise ValueError("Invalid profile photo format.")
            image.verify()
            source, captured = item["source"], item["captured"]
            if source not in {"unitv2-camera","robot-camera"} or not math.isfinite(captured) or captured <= 0: raise ValueError("Invalid profile photo source.")
            relative = f"media/face-profiles/{uuid.uuid4().hex}.png"
            path = self.path(relative)
            staged.append(path)
            with path.open("xb") as output:
                output.write(png)
                output.flush()
                __import__("os").fsync(output.fileno())
            row = db.execute("""INSERT INTO media(path,media_type,mime_type,source,captured,width,height,size_bytes,sha256,created,purpose)
                VALUES(?,'image','image/png',?,?,?,?,?,?,?,?)""",
                (relative,source,captured,image.width,image.height,len(png),hashlib.sha256(png).hexdigest(),time.time(),PURPOSE))
            ids.append(row.lastrowid)
        return ids

    def retire(self, db, person):
        db.execute("""UPDATE media SET deleted_at=? WHERE purpose=? AND id IN
            (SELECT reference_media_id FROM face_profiles WHERE person_id=?)""",(time.time(),PURPOSE,person))

    def cleanup(self, db):
        """Retry deletions after interruption; never touch observations or foreign paths."""
        failed = False
        for row in db.execute("""SELECT id,path FROM media WHERE purpose=? AND deleted_at IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM face_profiles WHERE reference_media_id=media.id)""",(PURPOSE,)).fetchall():
            try:
                self.path(row["path"]).unlink(missing_ok=True)
                db.execute("DELETE FROM media WHERE id=?",(row["id"],))
            except (OSError,ValueError): failed = True
        # A process kill between file creation and SQL commit can leave an orphan.
        # Grace period keeps in-flight writes by another process out of cleanup.
        known = {r[0] for r in db.execute("SELECT path FROM media WHERE purpose=?",(PURPOSE,))}
        if self.directory.exists() and not self.directory.is_symlink():
            for path in self.directory.glob("*.png"):
                relative = f"media/face-profiles/{path.name}"
                if relative in known: continue
                try:
                    owned = self.path(relative)
                    if owned.stat().st_mtime < time.time()-3600: owned.unlink()
                except (OSError,ValueError): continue
        return not failed

    def read(self, db, person):
        photos = []
        rows = db.execute("""SELECT m.* FROM face_profiles f JOIN media m ON m.id=f.reference_media_id
            JOIN persons p ON p.id=f.person_id WHERE f.person_id=? AND f.active=1 AND p.active=1
            AND m.purpose=? AND m.deleted_at IS NULL ORDER BY f.created_at,f.id LIMIT 3""",(person,PURPOSE))
        for row in rows:
            item = {"source":row["source"],"captured":row["captured"]}
            try:
                path = self.path(row["path"])
                with path.open("rb") as handle: png = handle.read(MAX_PHOTO_BYTES+1)
                if len(png) > MAX_PHOTO_BYTES or hashlib.sha256(png).hexdigest() != row["sha256"]:
                    raise ValueError("Photo changed.")
                item["png_base64"] = base64.b64encode(png).decode("ascii")
            except (OSError,ValueError): item["unavailable"] = True
            photos.append(item)
        return photos
