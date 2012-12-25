from gi.repository import GLib
import os
import logging
import gettext

# http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), 'trifle')

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
fmt = "%(levelname)-7s(%(relpath)s:%(lineno)s in %(funcName)s) %(msg)s"
verbose_handler = logging.StreamHandler()
verbose_handler.setFormatter(Formatter(fmt))
fmt = "%(levelname)-7s %(msg)s"
handler = logging.StreamHandler()
handler.setFormatter(Formatter(fmt))

# L11n
localedir = gettext.bindtextdomain('trifle')
_ = gettext.gettext
ngettext = gettext.ngettext

