# Is py2 or py3
try:
    import __builtin__
    __builtins = __builtin__.__dict__
    __builtins__['PY2'] = True
except:
    __builtins__['PY2'] = False

# Setup logging module
import logging
__builtins__['logger'] = logging.getLogger('lightread')
fmt_str = "%(levelname)s: %(name)s.%(funcName)s %(message)s"
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(logging.Formatter(fmt_str))
logger.addHandler(logging_handler)

# Setup localization
import gettext
localedir = gettext.bindtextdomain('lightread')
__builtins__['_'] = gettext.gettext
__builtins__['N_'] = gettext.ngettext
