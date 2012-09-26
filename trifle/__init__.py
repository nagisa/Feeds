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
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Setup logging module
__builtins__['logger'] = logging.getLogger('trifle')
fmt_str = "%(levelname)s: %(pathname)s:%(lineno)s %(message)s"
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(logging.Formatter(fmt_str))
logger.addHandler(logging_handler)

# Setup localization
localedir = gettext.bindtextdomain('trifle')
__builtins__['_'] = gettext.gettext
__builtins__['N_'] = gettext.ngettext

# Cache for application global variables
__builtins__['_globals_cache'] = {}

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
