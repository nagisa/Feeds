from gi.repository import Gtk, Gio
from lightread.views.windows import ApplicationWindow, LoginDialog
from lightread.models import auth
from lightread.models.feeds import AllItems


class Application(Gtk.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='net.launchpad.lightread',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('activate', self.on_activate)

    def on_activate(self, data=None):
        self.window = ApplicationWindow(self)
        self.window.show_all()

        auth.connect('ask-password', self.show_login_dialog)
        auth.login()

    def show_login_dialog(self, auth):
        # Should not show login dialog when internet is not available
        # Could not login, because credentials were incorrect
        login = LoginDialog(self.window)
        login.show_all()
