"""Módulo puente (v2): el código vive en app.modules.compare.photometry. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import photometry as _real

sys.modules[__name__] = _real
