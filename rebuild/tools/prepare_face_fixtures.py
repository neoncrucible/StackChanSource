"""Pinned upstream OpenCV evaluation media. Build/test only; never shipped."""
from pathlib import Path
import hashlib
import sys
import urllib.request

BASE='https://raw.githubusercontent.com/opencv/opencv_extra/4.13.0/testdata/cv/'
FILES={
    'david.webm':('tracking/david/data/david.webm',3917558,'4bbe69b7d097379af4d7ad128f02692820dc57a6d8275ea2b9e7eef4399a3e61'),
    'david1.jpg':('face/david1.jpg',19981,'378293e79d6802032c9f3596d2a70ab41ea3f52fc6c8b2f8ef5971541f9b32b4'),
    'david2.jpg':('face/david2.jpg',21695,'b39930fb7d57f4a14edc55d94ba1a002e9bffe323315b0423c223f7321a4e3cc'),
    '100032540_1.jpg':('face/100032540_1.jpg',189025,'bfe7d1d9bef715bca3d99b43733fc4c3812f4c43b71b8de4157482590e274037'),
    '100040721_1.jpg':('face/100040721_1.jpg',47493,'2400a116a262a719659fb770e74d22949b5a085c597d28917da9e92fa1ed7995'),
}


def prepare(directory):
    directory.mkdir(parents=True,exist_ok=True)
    for name,(path,size,digest) in FILES.items():
        destination=directory/name
        data=destination.read_bytes() if destination.exists() else b''
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:
            with urllib.request.urlopen(BASE+path,timeout=30) as response: data=response.read(size+1)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest: raise ValueError('Face fixture verification failed: '+name)
            destination.write_bytes(data)
        print('FACE_FIXTURE VERIFIED',name)
    return directory


if __name__=='__main__':prepare(Path(sys.argv[1]))
