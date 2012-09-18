from gi.repository import Gtk, Gio
from lightread.views.windows import ApplicationWindow, LoginDialog
from lightread.models import auth


class Application(Gtk.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='net.launchpad.lightread',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('activate', self.on_activate)

    def on_activate(self, data=None):
        self.window = ApplicationWindow()
        self.window.set_application(self)
        self.window.show_all()
        auth.secrets.connect('ask-password', self.show_login_dialog, None)

    def show_login_dialog(self, *args):
        # Should not show login dialog when internet is not available
        # Could not login, because credentials were incorrect
        def destroy_login_dialog(*args):
            auth.login()
            delattr(self, 'login')
        if not hasattr(self, 'login'):
            self.login = LoginDialog(transient_for=self.window, modal=True)
            self.login.show_all()
            self.login.connect('destroy', destroy_login_dialog)
