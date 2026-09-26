"""Módulo puente (v2): el código vive en app.core.jobs. Se mantiene para no romper imports antiguos."""
import sys

from app.core import jobs as _real

sys.modules[__name__] = _real
