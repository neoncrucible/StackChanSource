"""PyInstaller runtime hook for OpenCV's frozen package loader.

OpenCV removes its package wrapper and re-imports ``cv2`` to load the native
extension.  In a frozen application the wrapper can otherwise be found again
before the extension, leaving the loader recursing or waiting indefinitely.
The loader provides this flag specifically for packaged applications; it must
be set before the first ``import cv2``.
"""
import builtins
import sys

sys.OpenCV_REPLACE_SYS_PATH_0 = True
sys.OpenCV_LOADER_DEBUG = True

# Keep the loader's diagnostics out of the worker's JSON protocol while the
# packaged executable is being checked.  Normal application output is intact.
_kadence_print = builtins.print
def _kadence_cv2_print(*args, **kwargs):
    if args and isinstance(args[0], str) and args[0].startswith("OpenCV loader:"):
        kwargs["file"] = sys.stderr
    _kadence_print(*args, **kwargs)
builtins.print = _kadence_cv2_print
