"""Módulo puente (v2): el código vive en app.modules.compare.align. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import align as _real

sys.modules[__name__] = _real
