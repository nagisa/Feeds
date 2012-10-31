from gi.repository import Gtk, Gio, GLib
import os

from models.auth import auth
from models.settings import settings
from views.windows import ApplicationWindow, LoginDialog, PreferencesDialog, \
                          AboutDialog, SubscribeDialog
from views.notifications import notification
from views.utils import connect_once, get_data_path


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

    def on_activate(self, data=None):
        if self.window is not None:
            logger.critical('Window already exists')
            return

        self.init_app_menu()
        window = self.window = ApplicationWindow(show_menubar=True)
        window.set_application(self)
        window.show_all()

        # Connect and emit all important signals
        auth.secrets.connect('ask-password', self.on_login_dialog)

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
        window.main_toolbar.star.connect('toggled',
                                         window.item_view.on_star)
        window.main_toolbar.unread.connect('toggled',
                                           window.item_view.on_keep_unread)
        window.side_toolbar.mark_all.connect('clicked',
                                             window.items.on_all_read)
        self.connect('shutdown', self.on_shutdown)

        # Initial application state, default values, saved values, actions etc.
        window.side_toolbar.combobox.child.set_active_id('reading-list')
        if settings['start-refresh']:
            self.window.side_toolbar.refresh.emit('clicked')

        self.last_refresh = GLib.get_monotonic_time()
        # Check for need to refresh every 60 seconds.
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

    def on_show_prefs(self, *args):
        dialog = PreferencesDialog(transient_for=self.window, modal=True)
        dialog.show_all()

    def on_show_about(self, *args):
        dialog = AboutDialog(transient_for=self.window, modal=True)
        dialog.run()
        dialog.destroy()

    def on_refresh(self, button):
        self.window.side_toolbar.spinner.show()
        self.window.side_toolbar.refresh.set_sensitive(False)

        def on_sync_done(model, data=None):
            on_sync_done.to_finish -= 1
            if on_sync_done.to_finish == 0:
                self.window.side_toolbar.spinner.hide()
                self.window.side_toolbar.refresh.set_sensitive(True)
                self.last_refresh = GLib.get_monotonic_time()
            # If we can show notification
            if hasattr(model, 'unread_count') and model.unread_count > 0:
                count = model.unread_count
                summary = ngettext('You have an unread item',
                           'You have {0} unread items', count).format(count)
                if notification.closed or \
                            notification.get_property('summary') != summary:
                    notification.update(summary, '')
                    notification.show()
        on_sync_done.to_finish = 2

        # Do actual sync
        self.window.items.sync(on_sync_done)
        self.window.subscriptions.sync(on_sync_done)

    def on_subscribe(self, button):
        def on_subscribe_url(dialog):
            if dialog.url is None:
                return
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
        from models.utils import sqlite
        sqlite.force_commit()
