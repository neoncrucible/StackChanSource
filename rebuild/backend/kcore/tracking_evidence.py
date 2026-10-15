"""Local appearance evidence: a native rectangle alone is not a visible object."""
from __future__ import annotations


def signature(jpeg, box):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None: return None
    h,w = image.shape[:2]
    x,y,rw,rh = [round(v*s/b) for v,s,b in zip(box,(w,h,w,h),(640,480,640,480))]
    # Ignore the surrounding padding used to initialise the native tracker.
    inset_x,inset_y = max(1,rw//8),max(1,rh//8)
    patch = image[max(0,y+inset_y):min(h,y+rh-inset_y),max(0,x+inset_x):min(w,x+rw-inset_x)]
    if not patch.size: return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    saturated = (hsv[:,:,1]>70) & (hsv[:,:,2]>45)
    fraction = float(saturated.mean())
    mask = saturated.astype(np.uint8)*255 if fraction>.25 else None
    hist = cv2.calcHist([hsv],[0,1],mask,[18,8],[0,180,0,256])
    cv2.normalize(hist,hist,alpha=1,norm_type=cv2.NORM_L1)
    return hist, fraction, float(np.median(hsv[:,:,2]))


def agrees(reference, jpeg, box):
    import cv2
    current = signature(jpeg,box)
    if reference is None or current is None: return False
    old_hist,old_saturation,old_value = reference
    hist,saturation,value = current
    if old_saturation>.25 and saturation<old_saturation*.45: return False
    return cv2.compareHist(old_hist,hist,cv2.HISTCMP_BHATTACHARYYA)<.62 and abs(value-old_value)<100
