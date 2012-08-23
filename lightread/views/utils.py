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
