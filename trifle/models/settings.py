from gi.repository import Gio
from gi.repository import GLib

from trifle.utils import logger


class Settings(Gio.Settings):
    types = {'notifications': 'boolean', 'start-refresh': 'boolean',
             'refresh-every': 'uint16', 'cache-items': 'int16',
             'vertical-pos': 'uint16', 'horizontal-pos': 'uint16'}

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)

    def __getitem__(self, key):
        logger.debug(key)
        if key not in self.types:
            logger.warning('Key is not in types dictionary')
            return self.get_value(key)
        else:
            getter = 'get_{0}'.format(self.types[key])
            return getattr(self.get_value(key), getter)()

    def __setitem__(self, key, value):
        logger.debug('{0} = {1}'.format(key, value))
        if key not in self.types:
            logger.error('Cannot set value, because we don\'t know type (it\'s'
                         ' not in self.types')
            return
        value = getattr(GLib.Variant, 'new_{0}'.format(self.types[key]))(value)
        self.set_value(key, value)


settings = Settings('apps.trifle')
desktop = Settings('org.gnome.desktop.interface')
