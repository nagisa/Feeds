from gi.repository import Gtk, Gio, GLib

from trifle.models import auth
from trifle.models.settings import settings
from trifle.views.windows import ApplicationWindow, LoginDialog, AboutDialog,\
                           PreferencesDialog, SubscribeDialog
from trifle.views.notifications import notification
from trifle.views.utils import connect_once
from trifle.utils import logger, _, get_data_path


class Application(Gtk.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='apps.trifle',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('activate', self.on_activate)
        self.window = None

    def init_app_menu(self):
        actions = [('about', self.on_show_about),
                   ('preferences', self.on_show_prefs),
                   ('quit', lambda *x: self.quit())]
        for action, cb in actions:
            action = Gio.SimpleAction.new(action, None)
            action.connect('activate', cb)
            self.add_action(action)
        builder = Gtk.Builder(translation_domain='trifle')
        builder.add_from_file(get_data_path('ui', 'app-menu.ui'))
        self.set_app_menu(builder.get_object('app-menu'))

    def ensure_login(self, callback, retries=5):
        if retries < 5: # Hide the spinner we showed last time
            self.window.side_toolbar.spinner.hide()
        if retries < 0:
            self.report_error(_('Could not login due to network error'))
            return

        if auth.auth.status['ABORTED']:
            return
        elif auth.auth.status['OK'] and auth.auth.token_valid():
            return callback()
        else:
            if auth.auth.status['BAD_CREDENTIALS']:
                auth.keyring.invalidate_credentials()
            recall = lambda: self.ensure_login(callback, retries=retries - 1)
            self.window.side_toolbar.spinner.show()
            auth.auth.login(recall)

    def on_activate(self, data=None):
        if self.window is not None:
            logger.critical('Window already exists')
            return

        self.init_app_menu()
        window = self.window = ApplicationWindow(show_menubar=True)
        window.set_application(self)
        window.show_all()

        # Connect and emit all important signals
        auth.keyring.connect('ask-password', self.on_login_dialog)

        window.side_toolbar.combobox.child.connect('changed',
                                             window.items.on_cat_change)
        window.side_toolbar.combobox.child.connect('changed',
                                         window.subscriptions.on_cat_change)
        window.side_toolbar.refresh.connect('clicked', self.on_refresh)
        window.side_toolbar.subscribe.connect('clicked', self.on_subscribe)
        window.subscriptions.connect('cursor-changed',
                                     window.items.on_filter_change)
        window.items.connect('cursor-changed',
                             window.item_view.on_change)
        window.main_toolbar.starred.connect('toggled',
                                            window.item_view.on_star)
        window.main_toolbar.unread.connect('toggled',
                                           window.item_view.on_keep_unread)
        window.side_toolbar.mark_all.connect('clicked',
                                             window.items.on_all_read)
        window.item_view.connect('notify::item', lambda i_v, x:
                                 window.main_toolbar.set_item(i_v.item))
        self.connect('shutdown', self.on_shutdown)

        # Initial application state, default values, saved values, actions etc.
        window.side_toolbar.combobox.child.set_active_id('reading-list')
        if settings['start-refresh']:
            self.window.side_toolbar.refresh.emit('clicked')

        self.last_refresh = GLib.get_monotonic_time()
        # Check for need to refresh every 60 seconds.
        GLib.timeout_add_seconds(60, self.on_refresh_timeout)

    def on_login_dialog(self, keyring, callback):
        # TODO: Should not show login dialog when the internet is not available
        # Could not login, because credentials were incorrect
        def on_login_destroy(*args):
            callback()
            delattr(self, 'login')
        if not hasattr(self, 'login'):
            self.login = LoginDialog(transient_for=self.window, modal=True)
            self.login.show_all()
            self.login.connect('destroy', on_login_destroy)

    def on_show_prefs(self, *args):
        dialog = PreferencesDialog(transient_for=self.window, modal=True)
        dialog.show_all()

    def on_show_about(self, *args):
        dialog = AboutDialog(transient_for=self.window, modal=True)
        dialog.run()
        dialog.destroy()

    on_refresh = lambda s, *x: s.ensure_login(lambda: s._on_refresh(*x))
    def _on_refresh(self, button):
        def on_sync_done(model, data=None):
            on_sync_done.to_finish -= 1
            self.window.side_toolbar.spinner.hide()
            if on_sync_done.to_finish == 0:
                self.window.side_toolbar.refresh.set_sensitive(True)
            self.last_refresh = GLib.get_monotonic_time()
            if hasattr(model, 'unread_count') and model.unread_count > 0:
                notification.notify_unread_count(model.unread_count)
        on_sync_done.to_finish = 2

        # Show spinner twice, each for both synchronization works
        self.window.side_toolbar.spinner.show()
        self.window.side_toolbar.spinner.show()
        self.window.side_toolbar.refresh.set_sensitive(False)
        # Do actual sync
        self.window.items.sync(on_sync_done)
        self.window.subscriptions.sync(on_sync_done)

    def on_subscribe(self, button):
        def on_subscribe_url(dialog):
            if dialog.url is None:
                return
            self.ensure_login(lambda: _on_subscribe_url(dialog))

        def _on_subscribe_url(dialog):
            self.window.side_toolbar.spinner.show()
            subs_model = self.window.subscriptions.store
            subs_model.subscribe_to(dialog.url)
            connect_once(subs_model, 'subscribed',  on_subscribed)

        def on_subscribed(model, success, data=None):
            self.window.side_toolbar.spinner.hide()
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

    @staticmethod
    def on_shutdown(self):
        from trifle.models.utils import sqlite
        sqlite.force_commit()
