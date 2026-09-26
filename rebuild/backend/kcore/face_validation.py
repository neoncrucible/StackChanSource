"""Offline release check using upstream evaluation media, separate from profiles."""
from pathlib import Path
import io

from .local_faces import LocalFaces, match_details, similarity
from .face_sequence import FaceSequence


def replay_check(directory, *, models=None):
    import cv2
    from PIL import Image
    root=Path(directory)
    model=LocalFaces(root)
    if models is not None: model.directory=Path(models)
    model.preload()
    photos=[]
    for name in ('david1.jpg','david2.jpg','100032540_1.jpg','100040721_1.jpg'):
        image=Image.open(root/name).convert('RGB');image.thumbnail((640,480))
        encoded=io.BytesIO();image.save(encoded,format='PNG')
        faces,report=model.analyze_details(encoded.getvalue())
        if len(faces)!=1:raise RuntimeError('Fixture face detection failed')
        photos.append(faces[0])
    assert similarity(photos[0].embedding,photos[1].embedding)>.55
    assert all(similarity(photos[0].embedding,p.embedding)<.55 for p in photos[2:])
    video=cv2.VideoCapture(str(root/'david.webm'))
    samples=[];index=0;dim_usable=0
    try:
        while index<1000:
            ok,frame=video.read()
            if not ok:break
            if index%20==0 and index>=80:
                _,png=cv2.imencode('.png',frame)
                faces,report=model.analyze_details(png.tobytes())
                if len(faces)==1:
                    samples.append((index,faces[0]))
                    if index<160:dim_usable+=1
            index+=1
    finally:video.release()
    assert index==770 and dim_usable>=3
    # Disjoint source frames: enrollment and evaluation never share an image.
    training=[f for i,f in samples if i%40==0]
    evaluation=[f for i,f in samples if i%40==20]
    frontal=[f for i,f in samples if i in (160,200,240)]
    assert len(frontal)==3 and len(evaluation)>=15
    profile=[('fixture',f.embedding) for f in training]
    legacy=sum(match_details(f.embedding,[('fixture',p.embedding) for p in frontal])['person'] is not None for f in evaluation)
    matched=sum(match_details(f.embedding,profile)['person'] is not None for f in evaluation)
    assert matched>=15 and matched>legacy
    sequence=FaceSequence(profile)
    for face in evaluation:sequence.update([face])
    assert sequence.confirmed=={'fixture'}
    for stranger in photos[2:]:
        sequence=FaceSequence(profile)
        for _ in range(6):sequence.update([stranger])
        assert not sequence.confirmed
    return {'video_frames':index,'training_views':len(training),'held_out_views':len(evaluation),
            'matched_views':matched,'three_sample_matches':legacy,'different_people_rejected':2,'dim_views_usable':dim_usable}
