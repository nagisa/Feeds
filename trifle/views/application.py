from gi.repository import Gtk, Gio, GLib

from models.auth import auth
from models.settings import settings
from views.windows import ApplicationWindow, LoginDialog, PreferencesDialog, \
                          AboutDialog, SubscribeDialog
from views.notifications import notification
from views.utils import connect_once


class Application(Gtk.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='apps.trifle',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('activate', self.on_activate)

    def on_activate(self, data=None):
        window = self.window = ApplicationWindow()
        self.window.set_application(self)
        self.window.show_all()

        # Connect and emit all important signals
        auth.secrets.connect('ask-password', self.on_login_dialog)

        window.categories.connect('cursor-changed',
                                  window.itemsview.on_cat_change)
        window.categories.connect('cursor-changed',
                                  window.subsview.on_cat_change)
        window.sidebar_toolbar.refresh.connect('clicked', self.on_refresh)
        window.sidebar_toolbar.subscribe.connect('clicked', self.on_subscribe)
        window.subsview.connect('cursor-changed',
                                window.itemsview.on_filter_change)
        window.itemsview.connect('cursor-changed',
                                 window.feedview.on_change)
        window.feedview_toolbar.preferences.connect('clicked',
                                                    self.on_show_prefs)
        window.feedview_toolbar.star.connect('toggled',
                                             window.feedview.on_star)
        window.feedview_toolbar.unread.connect('toggled',
                                               window.feedview.on_keep_unread)

        if settings['start-refresh']:
            self.window.sidebar_toolbar.refresh.emit('clicked')

        self.last_refresh = GLib.get_monotonic_time()
        # Check every 60 seconds.
        GLib.timeout_add_seconds(60, self.on_refresh_timeout)

    def on_login_dialog(self, *args):
        # Should not show login dialog when internet is not available
        # Could not login, because credentials were incorrect
        def destroy_login_dialog(*args):
            auth.login()
            delattr(self, 'login')
        if not hasattr(self, 'login'):
            self.login = LoginDialog(transient_for=self.window, modal=True)
            self.login.show_all()
            self.login.connect('destroy', destroy_login_dialog)

    def on_show_prefs(self, button):
        dialog = PreferencesDialog(transient_for=self.window, modal=True)
        dialog.show_all()

    def on_show_about(self):
        dialog = AboutDialog(transient_for=self.window, modal=True)
        dialog.run()
        dialog.destroy()

    def on_refresh(self, button):
        self.window.display_spinner(True)
        self.window.sidebar_toolbar.refresh.set_sensitive(False)

        def on_sync_done(model, data=None):
            on_sync_done.to_finish -= 1
            if on_sync_done.to_finish == 0:
                self.window.display_spinner(False)
                self.window.sidebar_toolbar.refresh.set_sensitive(True)
                self.last_refresh = GLib.get_monotonic_time()
            # If we can show notification
            if hasattr(model, 'unread_count') and model.unread_count > 0:
                count = model.unread_count
                summary = N_('You have an unread item',
                           'You have {0} unread items', count).format(count)
                if notification.closed or \
                            notification.get_property('summary') != summary:
                    notification.update(summary, '')
                    notification.show()
        on_sync_done.to_finish = 2

        # Do actual sync
        self.window.itemsview.sync(on_sync_done)
        self.window.subsview.sync(on_sync_done)

    def on_subscribe(self, button):
        def on_subscribe_url(dialog):
            if dialog.url is None:
                return
            self.window.display_spinner(True)
            subs_model = self.window.subsview.store
            subs_model.subscribe_to(dialog.url)
            connect_once(subs_model, 'subscribed',  on_subscribed)

        def on_subscribed(model, success, data=None):
            self.window.display_spinner(False)
            if not success:
                logger.error('Could not subscribe to a feed')
                self.report_error(_('Could not subscribe to a feed'))
                return
            self.on_refresh(None)

        dialog = SubscribeDialog(transient_for=self.window, modal=True)
        dialog.show_all()
        dialog.connect('destroy', on_subscribe_url)

    def report_error(self, error):
        dfl = Gtk.DialogFlags.MODAL & Gtk.DialogFlags.DESTROY_WITH_PARENT
        dialog = Gtk.MessageDialog(self.window, dfl, Gtk.MessageType.ERROR,
                                   Gtk.ButtonsType.OK, error)
        dialog.run()
        dialog.destroy()

    def on_refresh_timeout(self):
        current = GLib.get_monotonic_time()
        refresh_every = settings['refresh-every']
        # Setting 'refresh-every' value 0 stands for Never
        if refresh_every == 0:
            self.last_refresh = current
            return True
        if current - self.last_refresh > refresh_every * 6E7:
            self.on_refresh(None)
        return True

