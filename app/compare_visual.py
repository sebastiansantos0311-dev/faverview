"""Módulo puente (v2): el código vive en app.modules.compare.compare_visual. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import compare_visual as _real

sys.modules[__name__] = _real
