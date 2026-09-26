"""Módulo puente (v2): el código vive en app.modules.compare.scoring. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import scoring as _real

sys.modules[__name__] = _real
