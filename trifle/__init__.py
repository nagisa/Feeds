import gettext
import logging
import os
import sys

# Add module to a path
__builtins__['MODULE_PATH'] = os.path.abspath(os.path.dirname(__file__))
sys.path.append(MODULE_PATH)

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
