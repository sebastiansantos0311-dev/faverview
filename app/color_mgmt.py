"""Módulo puente (v2): el código vive en app.core.color_mgmt. Se mantiene para no romper imports antiguos."""
import sys

from app.core import color_mgmt as _real

sys.modules[__name__] = _real
