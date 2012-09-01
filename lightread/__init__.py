# Is py2 or py3
try:
    import __builtin__
    __builtins__ = __builtin__.__dict__
    __builtins__['PY2'] = True
except:
    __builtins__['PY2'] = False

import gettext
import logging
import os

# Setup logging module
__builtins__['logger'] = logging.getLogger('lightread')
fmt_str = "%(levelname)s: %(name)s.%(funcName)s %(message)s"
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(logging.Formatter(fmt_str))
logger.addHandler(logging_handler)

# Setup localization
localedir = gettext.bindtextdomain('lightread')
__builtins__['_'] = gettext.gettext
__builtins__['N_'] = gettext.ngettext

# Cache for application global variables
__builtins__['_globals_cache'] = {}

# Directories
# Spec: http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
_CACHE_DIR = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
__builtins__['CACHE_DIR'] = os.path.join(_CACHE_DIR, 'lightread')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)