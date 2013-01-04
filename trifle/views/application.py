from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from trifle import models, views
from trifle.utils import logger, get_data_path, connect_once, sqlite


class Application(Gtk.Application):
    last_sync = GObject.property(type=object)
    _login_view = None

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='apps.trifle',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('startup', self.on_startup)
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)

    @GObject.property(type=views.windows.LoginDialog)
    def login_view(self):
        if self._login_view is None:
            self._login_view = views.windows.LoginDialog(modal=True)
        return self._login_view

    def ensure_login(self, callback):
        connect_once(self.login_view, 'logged-in', lambda *a: callback())
        self.login_view.set_transient_for(self.get_active_window())
        self.login_view.ensure_login()

    @staticmethod
    def on_startup(self):
        # Initialize application menu
        actions = [('synchronize', self.on_sync),
                   ('subscribe', self.on_subscribe),
                   ('about', self.on_show_about),
                   ('preferences', self.on_show_prefs),
                   ('quit', lambda *x: self.quit())]
        for action, cb in actions:
            action = Gio.SimpleAction.new(action, None)
            action.connect('activate', cb)
            self.add_action(action)
        builder = Gtk.Builder(translation_domain='trifle')
        builder.add_from_file(get_data_path('ui', 'app-menu.ui'))
        self.set_app_menu(builder.get_object('app-menu'))

        # Check for need to refresh every 60 seconds.
        GLib.timeout_add_seconds(60, self.on_sync_timeout)
        self.last_sync = GLib.get_monotonic_time()
        if models.settings.settings['start-refresh']:
            self.on_sync(None)

    @staticmethod
    def on_activate(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_path(get_data_path('ui', 'trifle-style.css'))
        ctx = Gtk.StyleContext()
        ctx.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        window = views.windows.ApplicationWindow()
        window.set_application(self)
        window.show_all()

    @staticmethod
    def on_shutdown(self):
        sqlite.force_commit()

    def on_show_prefs(self, action, data=None):
        props = {'modal': True, 'transient-for': self.get_active_window()}
        dialog = views.windows.PreferencesDialog(**props)
        dialog.show_all()

    def on_show_about(self, action, data=None):
        props = {'modal': True, 'transient-for': self.get_active_window()}
        dialog = views.windows.AboutDialog(**props)
        dialog.run()
        dialog.destroy()

    def on_subscribe(self, action, data=None):
        props = {'modal': True, 'transient-for': self.get_active_window(),
                 'login_view': self.login_view}
        dialog = views.windows.SubscribeDialog(**props)
        dialog.show_all()
        dialog.connect('subscribed', lambda *a: self.on_sync(None))

    on_sync = lambda s, *x: s.ensure_login(lambda: s._on_sync(*x))
    def _on_sync(self, action, data=None):
        def on_sync_done(synchronizer, data=None):
            self.last_sync = GLib.get_monotonic_time()

        def on_subscr_sync_done(synchronizer, data=None):
            for window in self.get_windows():
                window._builder.get_object('sub-view').store.update()

        def on_items_sync_done(synchronizer, data=None):
            for window in self.get_windows():
                window._builder.get_object('items-view').main_model.update()

            notification = views.notifications.notification
            unread = models.feeds.Store.unread_count()
            notification.notify_unread_count(unread)

        def on_flags_sync_done(synchronizer, data=None):
            def cb(*args):
                ids.sync()
                return False
            # Delay next stage so servers can clean up their caches.
            GLib.timeout_add_seconds(1, cb)

        logger.debug('Starting synchronization')
        auth = self.login_view.model
        # Items synchronization
        ids = models.synchronizers.Id(auth=auth)
        flags = models.synchronizers.Flags(auth=auth)
        items = models.synchronizers.Items(auth=auth)
        connect_once(flags, 'sync-done', on_flags_sync_done)
        connect_once(ids, 'sync-done', lambda *x: items.sync())
        connect_once(items, 'sync-done', on_sync_done)
        connect_once(items, 'sync-done', on_items_sync_done)
        flags.sync()
        # Subscriptions synchronization
        subscriptions = models.synchronizers.Subscriptions(auth=auth)
        icons = models.synchronizers.Favicons(auth=auth)
        connect_once(subscriptions, 'sync-done', lambda *x: icons.sync())
        connect_once(icons, 'sync-done', on_sync_done)
        connect_once(icons, 'sync-done', on_subscr_sync_done)
        subscriptions.sync()

    def on_sync_timeout(self):
        current = GLib.get_monotonic_time()
        refresh_every = models.settings.settings['refresh-every']
        # Setting 'refresh-every' value 0 stands for Never
        if refresh_every == 0:
            self.last_sync = current
            return True
        if current - self.last_sync > refresh_every * 6E7:
            self.on_sync(None)
        return True

    def on_ask_password(self, keyring, callback):
        # TODO: Should not show login dialog when the internet is not available
        # Could not login, because credentials were incorrect
        def on_destroy(dialog, callback):
            callback()

        props = {'modal': True, 'transient_for': self.get_active_window()}
        dialog = views.windows.LoginDialog(**props)
        dialog.show_all()
        dialog.connect('destroy', on_destroy, callback)
