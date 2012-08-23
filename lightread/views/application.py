from gi.repository import Gtk, Gio
from lightread.views.windows import ApplicationWindow


class Application(Gtk.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='net.launchpad.lightread',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('activate', self.on_activate)
        self.windows = []

    def on_activate(self, data=None):
        window = ApplicationWindow(self)
        self.windows.append(window)
        window.show_all()
