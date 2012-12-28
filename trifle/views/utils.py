from gi.repository import Gtk, Pango
import time

from trifle.utils import get_data_path, logger, _, ngettext

class BuiltMixin:
    def __new__(cls, *args, **kwargs):
        # Avoid getting __init__ called during building.
        try:
            cls_init = cls.__init__
            delattr(cls, '__init__')
        except AttributeError:
            cls_init = None

        builder = Gtk.Builder(translation_domain='trifle')
        path = get_data_path('ui', cls.ui_file)
        builder.add_from_file(path)
        parent = builder.get_object(cls.top_object)
        builder.connect_signals(parent)
        parent._builder = builder

        # But let it be executed when initializing object normally
        if cls_init is not None:
            cls.__init__ = cls_init
        return parent


def hexcolor(color):
    return '#{0:02X}{1:02X}{2:02X}'.format((color.red * 0xFF).__trunc__(),
                                           (color.green * 0xFF).__trunc__(),
                                           (color.blue * 0xFF).__trunc__())

def parse_font(string):
    font = Pango.font_description_from_string(string)
    if font is None:
        return (None, None)
    return (font.get_family(), font.get_size() / Pango.SCALE)


def time_ago(timestamp):
    ago_fmt = _('{0} ago')
    seconds = (time.time() - timestamp).__trunc__()
    if seconds < 0:
        logger.warning('Invalid timestamp occured')
        return _('From the future')
    if seconds < 60:
        return _('Just now')

    minutes = (seconds / 60).__trunc__()
    min_fmt = ngettext('{0} minute', '{0} minutes', minutes)
    if minutes < 60:
        return ago_fmt.format(min_fmt.format(minutes))

    hours = (minutes / 60).__trunc__()
    hour_fmt = ngettext('{0} hour', '{0} hours', hours)
    if hours < 24:
        return ago_fmt.format(hour_fmt.format(hours))

    days = (hours / 24).__trunc__()
    day_fmt = ngettext('{0} day', '{0} days', days)
    return ago_fmt.format(day_fmt.format(days))


def connect_once(obj, signal, callback, data=None):
    def disconnect_and_callback(callback):
        def handler(*args, **kwargs):
            obj.disconnect(cnn_id)
            callback(*args, **kwargs)
        return handler
    cnn_id = obj.connect(signal, disconnect_and_callback(callback), data)
