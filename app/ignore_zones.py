"""Módulo puente (v2): el código vive en app.modules.compare.ignore_zones. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import ignore_zones as _real

sys.modules[__name__] = _real
