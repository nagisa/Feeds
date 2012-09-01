from gi.repository import Gtk
from datetime import datetime


class ScrollWindowMixin:
    """ Provides scrollwindow read-only property which contains a ScrollWindow
    widget with self added to it. """

    @property
    def scrollwindow(self):
        if not hasattr(self, '_scrollwindow_widget'):
            self._scrollwindow_widget = Gtk.ScrolledWindow()
            self._scrollwindow_widget.add(self)
        return self._scrollwindow_widget


def hexcolor(color):
    return '#{0:02X}{1:02X}{2:02X}'.format(round(color.red * 0xFF),
                                           round(color.green * 0xFF),
                                           round(color.blue * 0xFF))
def time_ago(datetime):
    diff = datetime.now() - datetime
    hours = (diff.seconds / 3600).__trunc__()
    if diff.days > 0:
        return "{0} {1}".format(
               N_("{0} day", "{0} days", diff.days).format(diff.days),
               N_("{0} hour ago", "{0} hours ago", hours).format(hours))
    elif hours > 0:
        return N_("{0} hour ago", "{0} hours ago", hours).format(hours)
    else:
        minutes = (diff.seconds / 60).__trunc__()
        return N_("{0} minute ago", "{0} minutes ago", minutes).format(minutes)
