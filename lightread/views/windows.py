import copy
from gi.repository import Gtk, WebKit
from lightread.models import settings, auth
from lightread.views import widgets, utils
from lightread.utils import get_data_path


class ApplicationWindow(Gtk.ApplicationWindow):

    def __init__(self, application, *args, **kwargs):
        self.application = application
        if not kwargs.get('application', None):
            kwargs['application'] = application
        super(ApplicationWindow, self).__init__(*args, **kwargs)

        # Metadata.
        self.set_wmclass('lightread', 'lightread')
        self.set_title('Lightread')
        self.set_default_size(1280, 1024)
        # We probably always want it maximized on start.
        self.maximize()
        # And we don't care about title bar. Very likely.
        self.set_hide_titlebar_when_maximized(True)

        # Adding widgets to window
        base_box = Gtk.VBox()
        self.add(base_box)

        self.toolbar = widgets.Toolbar()
        base_box.pack_start(self.toolbar, False, False, 0)
        self.toolbar.preferences.connect('clicked', self.show_prefs)

        main_view = Gtk.HPaned()
        base_box.pack_start(main_view, True, True, 0)

        side_view = widgets.Sidebar()
        main_view.pack1(side_view, True, False)

        # Webview in the left
        self.feedview = widgets.FeedView()
        self.feedview.load_uri('http://www.duckduckgo.com/')
        main_view.pack2(self.feedview.scrollwindow, True, False)
        main_view.set_position(1)

    def show_prefs(self, data=None):
        dialog = PreferencesDialog(self)
        dialog.show_all()

    def show_about(self, data=None):
        dialog = AboutDialog(self)
        dialog.run()
        dialog.destroy()


class PreferencesDialog(utils.BuiltMixin, Gtk.Dialog):
    ui_file = 'lightread-preferences.ui'
    top_object = 'preferences-dialog'

    def __init__(self, parent, *args, **kwargs):
        self.set_modal(True)
        self.set_transient_for(parent)
        self.connect('response', self.on_response)

        for cb_name in ['notifications', 'start-refresh']:
            checkbox = self.builder.get_object(cb_name)
            checkbox.set_active(settings[cb_name])
            checkbox.connect('toggled', self.on_toggle, cb_name)

        refresh = self.builder.get_object('refresh-every')
        for time, label in ((0, _('Never')), (5, _('5 minutes')),
                            (10, _('10 minutes')), (30, _('30 minutes')),
                            (60, _('1 hour'))):
            refresh.append(str(time), label)
        refresh.set_active_id(str(settings['refresh-every']))
        refresh.connect('changed', self.on_change, 'refresh-every')

        adjustment = self.builder.get_object('cache-upto-value')
        adjustment.set_value(settings['cache-items'])
        adjustment.connect('value-changed', self.on_val_change, 'cache-items')

    def on_change(widget, setting):
        settings[setting] = int(widget.get_active_id())

    def on_val_change(adj, setting):
        settings[setting] = adj.get_value()

    def on_toggle(widget, setting):
        settings[setting] = widget.get_active()

    def on_response(self, r):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.OK):
            self.destroy()


class AboutDialog(utils.BuiltMixin, Gtk.AboutDialog):
    ui_file = 'lightread-about.ui'
    top_object = 'about-dialog'

    def __init__(self, parent, *args, **kwargs):
        self.set_modal(True)
        self.set_transient_for(parent)


class LoginDialog(utils.BuiltMixin, Gtk.Dialog):
    """
    This dialog will ensure, that user becomes logged in by any means
    """
    ui_file = 'lightread-login.ui'
    top_object = 'login-dialog'

    def __init__(self, parent, *args, **kwargs):
        self.set_modal(True)
        self.set_transient_for(parent)
        self.user_entry = self.builder.get_object('username')
        self.passwd_entry = self.builder.get_object('password')
        self.msg = Gtk.Label()
        self.builder.get_object('message').pack_start(self.msg, False, True, 0)
        self.user_entry.connect('activate', self.on_activate, self)
        self.passwd_entry.connect('activate', self.on_activate, self)
        self.connect('response', self.on_response)

    def on_response(self, r):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            self.destroy()
            return
        user = self.builder.get_object('username').get_text()
        password = self.builder.get_object('password').get_text()
        logger.debug('username={0} and passwd is {1} chr long'.format(
                     user, len(password)))
        if len(password) == 0 or len(user) == 0:
            self.msg.set_text(_('All fields are required'))
            return False
        auth.secrets.set(user, password)
        self.destroy()

    def on_activate(entry, self):
        self.emit('response', 0)
