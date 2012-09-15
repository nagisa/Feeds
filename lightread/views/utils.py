import time
import html
from gi.repository import Gtk, Pango
from lightread.utils import get_data_path


class ScrollWindowMixin:
    """ Provides scrollwindow read-only property which contains a ScrollWindow
    widget with self added to it. """

    @property
    def scrollwindow(self):
        if not hasattr(self, '_scrollwindow_widget'):
            self._scrollwindow_widget = Gtk.ScrolledWindow()
            self._scrollwindow_widget.add(self)
        return self._scrollwindow_widget


class BuiltMixin:

    def __new__(cls, *args, **kwargs):
        builder = Gtk.Builder(translation_domain='lightread')
        path = get_data_path('ui', cls.ui_file)
        builder.add_from_file(path)
        new_obj = builder.get_object(cls.top_object)
        new_obj.builder = builder
        for attr, value in cls.__dict__.items():
            setattr(new_obj, attr, value)
        # Call __init__, somewhy it doesn't do so automatically.
        new_obj.__init__(new_obj, *args, **kwargs)
        return new_obj


def hexcolor(color):
    return '#{0:02X}{1:02X}{2:02X}'.format(round(color.red * 0xFF),
                                           round(color.green * 0xFF),
                                           round(color.blue * 0xFF))


def time_ago(timestamp):
    ago_fmt = _('{0} ago')
    seconds = (time.time() - timestamp).__trunc__()
    if seconds < 0:
        logger.warning('Invalid timestamp occured')
        return _('From the future')
    if seconds < 60:
        return _('Just now')

    minutes = (seconds / 60).__trunc__()
    min_fmt = N_('{0} minute', '{0} minutes', minutes)
    if minutes < 60:
        return ago_fmt.format(min_fmt.format(minutes))

    hours = (minutes / 60).__trunc__()
    hour_fmt = N_('{0} hour', '{0} hours', hours)
    if hours < 24:
        return ago_fmt.format(hour_fmt.format(hours))

    days = (hours / 24).__trunc__()
    day_fmt = N_('{0} day', '{0} days', days)
    return ago_fmt.format(day_fmt.format(days))
