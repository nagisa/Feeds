from gi.repository import Gtk, GObject, Gio

from trifle import models
from trifle.utils import VERSION, _, logger
from trifle.views import utils


class ApplicationWindow(utils.BuiltMixin, Gtk.ApplicationWindow):
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
        item_view.item_id = row[0]
        toolbar.set_properties(timestamp=row[4], title=row[1], uri=row[3],
                               unread=False, starred=row[6])
        row[11], row[5] = True, False

    def on_star(self, toolbar, gprop):
        item_view = self._builder.get_object('item-view')
        items = self._builder.get_object('items-view')
        item_id = item_view.item_id
        for row in items.reading_list:
            if row[0] == item_id:
                row[11], row[6] = True, toolbar.starred
                return
        logger.error("Couldn't set star for item {0}, it doesn't exist"
                                                             .format(item_id))

    def on_keep_unread(self, toolbar, gprop):
        item_view = self._builder.get_object('item-view')
        items = self._builder.get_object('items-view')
        item_id = item_view.item_id
        for row in items.reading_list:
            if row[0] == item_id:
                row[11], row[5] = True, toolbar.unread
                return
        logger.error("Couldn't make item {0} unread, it doesn't exist"
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


class PreferencesDialog(utils.BuiltMixin, Gtk.Dialog):
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


class AboutDialog(utils.BuiltMixin, Gtk.AboutDialog):
    ui_file = 'about-dialog.ui'
    top_object = 'about-dialog'

    def __init__(self, *args, **kwargs):
        self.set_properties(version=VERSION, **kwargs)


class LoginDialog(utils.BuiltMixin, Gtk.Dialog):
    """
    This view will ensure, that user becomes logged in. It may fail in some
    cases tough:
    * There is no internet
    * User decides to click cancel button or quit the dialog any other way.
    """
    ui_file = 'login-dialog.ui'
    top_object = 'login-dialog'

    max_retries = GObject.property(type=GObject.TYPE_UINT)
    retries = GObject.property(type=GObject.TYPE_UINT)
    report_error = GObject.property(type=object)

    def __init__(self, *args, **kwargs):
        super(LoginDialog, self).__init__(*args, **kwargs)
        models.auth.keyring.connect('ask-password', self.on_ask_password)

    def ensure_login(self, callback):
        self.retries = self.max_retries
        if models.auth.auth.status['OK'] and models.auth.auth.token_valid():
            return callback()
        models.auth.auth.login(lambda: self.on_login(callback))

    def on_login(self, callback):
        self.retries -= 1
        if self.retries < 0:
            if self.report_error is not None:
                self.report_error('Could not login')
            return

        if models.auth.auth.status['ABORTED']:
            return
        elif models.auth.auth.status['BAD_CREDENTIALS']:
            models.auth.keyring.invalidate_credentials()
            models.auth.auth.login(lambda: self.on_login(callback))

    def on_ask_password(self, keyring, callback):
        self.password_cb = callback
        self.connect('response', self.on_response, callback)
        self.show_all()

    def on_response(self, dialog, r, callback):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            callback(None, None)
            self.hide()
            return

        user_entry = self._builder.get_object('username')
        passwd_entry = self._builder.get_object('password')

        if 0 in (len(passwd_entry.get_text()), len(user_entry.get_text())):
            msg = _('All fields are required')
            self._builder.get_object('error-label').set_text(msg)
            self._builder.get_object('error-bar').show()
            return False
        callback(user_entry.get_text(), passwd_entry.get_text())
        self.hide()

    def on_activate(self, entry, data=None):
        self.emit('response', 0)


class SubscribeDialog(utils.BuiltMixin, Gtk.Dialog):
    """
    This dialog will ensure, that user becomes logged in by any means
    """
    ui_file = 'subscribe-dialog.ui'
    top_object = 'subscribe-dialog'

    def on_response(self, dialog, r, data=None):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            self.destroy()
            return
        uri = self._builder.get_object('uri')
        if len(uri.get_text()) == 0:
            self._builder.get_object('error-bar').show()
            return
        # If we've shown any errors before, hide them
        self._builder.get_object('error-bar').hide()
        # Show a progress spinner
        spinner = self._builder.get_object('progress')
        spinner.show()
        logger.debug('Subscribing to {0}'.format(uri.get_text()))

    def on_activate(self, entry, data=None):
        self.emit('response', 0)

GObject.type_register(ApplicationWindow)
GObject.type_register(PreferencesDialog)
GObject.type_register(AboutDialog)
GObject.type_register(LoginDialog)
GObject.type_register(SubscribeDialog)
