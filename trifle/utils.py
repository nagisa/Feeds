import os
import logging
import gettext

# Directories
# Spec: http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
CACHE_DIR = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
CACHE_DIR = os.path.join(CACHE_DIR, 'trifle')

VERSION_INFO = (1, 0)
VERSION = '.'.join(str(part) for part in VERSION_INFO)
MODULE_PATH = os.path.abspath(os.path.dirname(__file__))

def get_data_path(*args):
    """ Constructs absolute path to data file """
    path = os.path.join(MODULE_PATH, 'data', *args)
    if not os.path.exists(path):
        logger.warning('Constructed path \'{0}\' does not exist'.format(path))
    return path

# Logging
class Formatter(logging.Formatter):
    def format(self, record):
        relpath = os.path.relpath(record.pathname, MODULE_PATH)
        record.relpath = relpath
        return super(Formatter, self).format(record)

logger = logging.getLogger('trifle')
fmt = "%(levelname).7s\t%(lineno)4s |%(relpath)20.20s in %(funcName)15.15s" \
      " %(msg)s"
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(Formatter(fmt))
logger.addHandler(logging_handler)

# L11n
localedir = gettext.bindtextdomain('trifle')
_ = gettext.gettext
ngettext = gettext.ngettext

