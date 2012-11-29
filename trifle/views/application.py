from gi.repository import Gtk, Gio, GLib, GObject

from trifle import models, views
from trifle.views.utils import connect_once
from trifle.utils import logger, _, get_data_path


class Application(Gtk.Application):
    last_sync = GObject.property(type=object)

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args,
                                          application_id='apps.trifle',
                                          flags=Gio.ApplicationFlags.FLAGS_NONE,
                                          **kwargs)
        self.connect('startup', self.on_startup)
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)
        models.auth.keyring.connect('ask-password', self.on_login_dialog)

    def ensure_login(self, callback, retries=5):
        if retries < 0:
            self.report_error(_('Could not login due to network error'))
            return

        if models.auth.auth.status['ABORTED']:
            return
        elif models.auth.auth.status['OK'] and models.auth.auth.token_valid():
            return callback()
        else:
            if models.auth.auth.status['BAD_CREDENTIALS']:
                models.auth.keyring.invalidate_credentials()
            recall = lambda: self.ensure_login(callback, retries=retries - 1)
            models.auth.auth.login(recall)

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
        window = views.windows.ApplicationWindow()
        window.set_application(self)
        window.show_all()

    @staticmethod
    def on_shutdown(self):
        models.utils.sqlite.force_commit()

    def on_show_prefs(self, action, data=None):
        props = {'modal': True, 'transient_for': self.get_active_window()}
        dialog = views.windows.PreferencesDialog(**props)
        dialog.show_all()

    def on_show_about(self, action, data=None):
        props = {'modal': True, 'transient_for': self.get_active_window()}
        dialog = views.windows.AboutDialog(**props)
        dialog.run()
        dialog.destroy()

    def on_subscribe(self, action, data=None):
        def on_subscribe_url(dialog):
            if dialog.url is None:
                return
            self.ensure_login(lambda: _on_subscribe_url(dialog))

        def _on_subscribe_url(dialog):
            subs_model = self.window.subscriptions.store
            subs_model.subscribe_to(dialog.url)
            connect_once(subs_model, 'subscribed',  on_subscribed)

        def on_subscribed(model, success, data=None):
            if not success:
                logger.error('Could not subscribe to a feed')
                self.report_error(_('Could not subscribe to a feed'))
                return
            self.on_sync(None)

        props = {'modal': True, 'transient_for': self.get_active_window()}
        dialog = views.windows.SubscribeDialog(**props)
        dialog.show_all()
        dialog.connect('destroy', on_subscribe_url)

    on_sync = lambda s, *x: s.ensure_login(lambda: s._on_sync(*x))
    def _on_sync(self, action, data=None):
        def on_sync_done(synchronizer, data=None):
            self.last_sync = GLib.get_monotonic_time()
            # if hasattr(model, 'unread_count') and model.unread_count > 0:
            #     notification.notify_unread_count(model.unread_count)

        ids = models.synchronizers.Id()
        flags = models.synchronizers.Flags()
        items = models.synchronizers.Items()
        subscriptions = models.synchronizers.Subscriptions()
        icons = models.synchronizers.Favicons()
        logger.debug('Starting synchronization')
        connect_once(flags, 'sync-done', lambda *x: ids.sync())
        connect_once(ids, 'sync-done', lambda *x: items.sync())
        connect_once(items, 'sync-done', on_sync_done)
        connect_once(subscriptions, 'sync-done', lambda *x: icons.sync())
        # TODO: Also ask to update model
        connect_once(icons, 'sync-done', on_sync_done)
        flags.sync()
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

    def on_login_dialog(self, keyring, callback):
        # TODO: Should not show login dialog when the internet is not available
        # Could not login, because credentials were incorrect
        def on_login_destroy(*args):
            callback()
            delattr(self, 'login')
        if not hasattr(self, 'login'):
            props = {'modal': True, 'transient_for': self.get_active_window()}
            self.login = views.windows.LoginDialog(**props)
            self.login.show_all()
            self.login.connect('destroy', on_login_destroy)


    def report_error(self, error):
        dfl = Gtk.DialogFlags.MODAL & Gtk.DialogFlags.DESTROY_WITH_PARENT
        dialog = Gtk.MessageDialog(self.window, dfl, Gtk.MessageType.ERROR,
                                   Gtk.ButtonsType.OK, error)
        dialog.run()
        dialog.destroy()

