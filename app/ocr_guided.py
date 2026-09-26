"""Módulo puente (v2): el código vive en app.modules.compare.ocr_guided. Se mantiene para no romper imports antiguos."""
import sys

from app.modules.compare import ocr_guided as _real

sys.modules[__name__] = _real
