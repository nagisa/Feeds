# Is py2 or py3
try:
    import __builtin__
    __builtins__ = __builtin__.__dict__
    __builtins__['PY2'] = True
except ImportError:
    __builtins__['PY2'] = False

import gettext
import logging
import os
import sys

# Add module to a path
__builtins__['MODULE_PATH'] = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, MODULE_PATH)

# Setup logging module
class Formatter(logging.Formatter):
    def format(self, record):
        relpath = os.path.relpath(record.pathname, MODULE_PATH)
        record.relpath = relpath
        return super(Formatter, self).format(record)

__builtins__['logger'] = logging.getLogger('trifle')
fmt = "%(levelname).7s\t%(lineno)4s |%(relpath)20.20s in %(funcName)15.15s %(msg)s"
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(Formatter(fmt))
logger.addHandler(logging_handler)

# Setup localization
localedir = gettext.bindtextdomain('trifle')
__builtins__['_'] = gettext.gettext
__builtins__['ngettext'] = gettext.ngettext

# Directories
# Spec: http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
_CACHE_DIR = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
__builtins__['CACHE_DIR'] = os.path.join(_CACHE_DIR, 'trifle')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


# I want my strings unicode!
def it_is_unicode(item):
    if not PY2:
        return item
    else:
        return item.decode('utf-8')
__builtins__['u'] = it_is_unicode
