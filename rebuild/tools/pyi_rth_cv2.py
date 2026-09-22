"""PyInstaller runtime hook for OpenCV's frozen package loader.

OpenCV removes its package wrapper and re-imports ``cv2`` to load the native
extension.  In a frozen application the wrapper can otherwise be found again
before the extension, leaving the loader recursing or waiting indefinitely.
The loader provides this flag specifically for packaged applications; it must
be set before the first ``import cv2``.
"""
import sys

sys.OpenCV_REPLACE_SYS_PATH_0 = True
