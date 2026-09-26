"""Módulo puente (v2): el código vive en app.modules.compare.compare_text. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import compare_text as _real

sys.modules[__name__] = _real
