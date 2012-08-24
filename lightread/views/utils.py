from gi.repository import Gtk


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
