from gi.repository import Gtk, GObject, Gio
from gettext import gettext as _

from trifle import models
from trifle.utils import VERSION, logger, ItemsColumn, BuiltMixin, connect_once


class ApplicationWindow(BuiltMixin, Gtk.ApplicationWindow):
    ui_file = 'window.ui'
    top_object = 'main-window'

    def __init__(self, *args, **kwargs):
        self.set_wmclass('Trifle', 'Trifle')

    @staticmethod
    def on_realize(self):
        self.maximize() # Should we really do that by default?

    def on_toolbar_category(self, toolbar, gprop):
        self._builder.get_object('items-view').set_category(toolbar.category)
        self._builder.get_object('sub-view').on_cat_change(toolbar.category)

    def on_subscr_change(self, selection):
        model, itr = selection.get_selected()
        if itr is not None:
            row = model[itr]
            items = self._builder.get_object('items-view')
            items.set_properties(subscription=row[1],
                                 sub_is_feed = row[0] == 1)

    def on_item_change(self, selection):
        model, itr = selection.get_selected()
        if model is None or itr is None:
            return
        row = model[itr]

        toolbar = self._builder.get_object('toolbar')
        item_view = self._builder.get_object('item-view')
        item_view.item_id = row[ItemsColumn.ID]
        toolbar.set_properties(timestamp=row[ItemsColumn.TIMESTAMP],
                               title=row[ItemsColumn.TITLE],
                               uri=row[ItemsColumn.LINK],
                               unread=False, starred=row[ItemsColumn.STARRED])
        row[ItemsColumn.FORCE_VISIBLE], row[ItemsColumn.UNREAD] = True, False

    def on_star(self, toolbar, gprop):
        self._on_item_status(ItemsColumn.STARRED, toolbar.starred)

    def on_keep_unread(self, toolbar, gprop):
        self._on_item_status(ItemsColumn.UNREAD, toolbar.unread)

    # Convenience method for on_star and on_keep_unread
    def _on_item_status(self, column, value):
        item_view = self._builder.get_object('item-view')
        items = self._builder.get_object('items-view')
        item_id = item_view.item_id
        for row in items.main_model:
            if row[ItemsColumn.ID] == item_id:
                row[ItemsColumn.FORCE_VISIBLE] = True
                row[column] = value
                return
        logger.error("Couldn't set status for item {0}, it doesn't exist"
                                                             .format(item_id))

    # TODO: These doesn't work correctly.
    # def on_horiz_pos_change(self, paned, gprop):
    #     print('horiz_change')
    #     paned = self._builder.get_object('paned')
    #     models.settings.settings['horizontal-pos'] = paned.props.position

    # def on_vert_pos_change(self, paned, gprop):
    #     paned_side = self._builder.get_object('paned-side')
    #     print(paned_side.get_visible(), paned_side.get_mapped())
    #     if not paned_side.get_mapped():
    #         return
    #     models.settings.settings['vertical-pos'] = paned_side.props.position


class PreferencesDialog(BuiltMixin, Gtk.Dialog):
    ui_file = 'preferences-dialog.ui'
    top_object = 'preferences-dialog'

    @staticmethod
    def on_realize(self):
        settings = models.settings.settings
        DEFAULT = Gio.SettingsBindFlags.DEFAULT

        for setting in ['notifications', 'start-refresh']:
            checkbox = self._builder.get_object(setting)
            settings.bind(setting, checkbox, 'active', DEFAULT)

        refresh = self._builder.get_object('refresh-every')
        refresh.set_active_id(str(models.settings.settings['refresh-every']))

        adjustment = self._builder.get_object('cache-upto-value')
        settings.bind('cache-items', adjustment, 'value', DEFAULT)

    def on_refresh_change(self, widget):
        models.settings.settings['refresh-every'] = int(widget.get_active_id())

    def on_response(self, dialog, r):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.OK):
            self.destroy()


class AboutDialog(BuiltMixin, Gtk.AboutDialog):
    ui_file = 'about-dialog.ui'
    top_object = 'about-dialog'

    def __init__(self, *args, **kwargs):
        self.set_properties(version=VERSION, **kwargs)


class LoginDialog(BuiltMixin, Gtk.Dialog):
    """
    This view will ensure, that user becomes logged in. It may fail in some
    cases tough:
    * There is no internet
    * User decides to click cancel button or quit the dialog any other way.
    """
    ui_file = 'login-dialog.ui'
    top_object = 'login-dialog'

    model = GObject.property(type=GObject.Object)
    keyring = GObject.property(type=models.auth.Keyring)

    __gsignals__ = {
        'logged-in': (GObject.SignalFlags.RUN_LAST, None, [])
    }

    def __init__(self, *args, **kwargs):
        super(LoginDialog, self).__init__(*args, **kwargs)
        if self.keyring is None:
            self.keyring = models.auth.SecretKeyring()
        if self.model is None:
            self.model = models.auth.Auth(keyring=self.keyring)

        self.keyring.connect('ask-password', self.on_ask_password)
        self.model.connect('notify::status', self.on_login_status_change)
        self.connect('response', self.on_response)

    @GObject.property
    def logged_in(self):
        return self.model.status['OK'] and self.model.token_valid()

    def ensure_login(self):
        if self.logged_in:
            # OK, good to go
            self.emit('logged-in')
            return
        if not self.model.status['PROGRESS']:
            self.model.login()

    def on_ask_password(self, keyring):
        self.show_all()
        self._builder.get_object('login').set_sensitive(True)
        self._builder.get_object('close').set_sensitive(True)
        self._builder.get_object('progress-spinner').hide()

    def on_login_status_change(self, model, gprop, data=None):
        if model.status['PROGRESS'] or model.status['ABORTED']:
            return # Ignore all in-progress updates and fails due to user.
        elif model.status['BAD_CREDENTIALS'] or not model.status['OK']:
            if model.status['BAD_CREDENTIALS']:
                msg = _('The username or password you entered is incorrect')
            else:
                msg = _('Could not login')
            self._builder.get_object('error-label').set_text(msg)
            self._builder.get_object('error-bar').show()
            self._builder.get_object('login').set_sensitive(True)
            self._builder.get_object('close').set_sensitive(True)
            self._builder.get_object('progress-spinner').hide()
            self.show_all()
        elif model.status['OK']:
            self.emit('logged-in')
            self.hide()

    def on_response(self, dialog, r):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            self.keyring.credentials_response(None, None)
            self.hide()
            return

        user_entry = self._builder.get_object('username')
        passwd_entry = self._builder.get_object('password')

        if 0 in (len(passwd_entry.get_text()), len(user_entry.get_text())):
            msg = _('All fields are required')
            self._builder.get_object('error-label').set_text(msg)
            self._builder.get_object('error-bar').show()
            self._builder.get_object('login').set_sensitive(True)
            self._builder.get_object('close').set_sensitive(True)
            self._builder.get_object('progress-spinner').hide()
            return False

        self._builder.get_object('login').set_sensitive(False)
        self._builder.get_object('close').set_sensitive(False)
        self._builder.get_object('progress-spinner').show()
        self._builder.get_object('error-bar').hide()
        self.keyring.credentials_response(user_entry.get_text(),
                                          passwd_entry.get_text())
        if not self.model.status['PROGRESS']:
            # We are not in progress, so we should start logging in
            self.model.login()

    def on_activate(self, entry, data=None):
        self.emit('response', 0)


class SubscribeDialog(BuiltMixin, Gtk.Dialog):
    ui_file = 'subscribe-dialog.ui'
    top_object = 'subscribe-dialog'
    login_view = GObject.property(type=GObject.Object)
    __gsignals__ = {
        'subscribed': (GObject.SignalFlags.RUN_LAST, None, [])
    }

    def __init__(self, *args, **kwargs):
        super(SubscribeDialog, self).__init__(*args, **kwargs)
        if self.login_view is None:
            self.login_view = LoginDialog(modal=True)

    def on_response(self, dialog, r, data=None):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            self.destroy()
            return
        uri = self._builder.get_object('uri')
        if len(uri.get_text()) == 0:
            msg = _('All fields are required')
            self._builder.get_object('error-bar').show()
            self._builder.get_object('error-label').set_text(msg)
            return

        self._builder.get_object('error-bar').hide()
        self._builder.get_object('progress').show()

        logger.debug('Subscribing to {0}'.format(uri.get_text()))
        auth = self.login_view.model
        subscriptions = models.synchronizers.Subscriptions(auth=auth)
        callback = lambda *a: subscriptions.subscribe_to(uri.get_text())
        connect_once(self.login_view, 'logged-in', callback)
        connect_once(subscriptions, 'subscribed', self.on_subscribed)
        self.login_view.set_transient_for(self)
        self.login_view.ensure_login()

    def on_subscribed(self, subscr, success, data=None):
        if not success:
            msg = _('Could not subscribe to a feed')
            self._builder.get_object('error-bar').show()
            self._builder.get_object('error-label').set_text(msg)
            self._builder.get_object('progress').hide()
        else:
            self.emit('subscribed')
            self.destroy()

    def on_activate(self, entry, data=None):
        self.emit('response', 0)

GObject.type_register(ApplicationWindow)
GObject.type_register(PreferencesDialog)
GObject.type_register(AboutDialog)
GObject.type_register(LoginDialog)
GObject.type_register(SubscribeDialog)
