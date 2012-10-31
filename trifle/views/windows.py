from gi.repository import Gtk, GObject


from trifle.utils import VERSION
from models.auth import auth
from models.settings import settings
from views import widgets, utils


class ApplicationWindow(utils.BuiltMixin, Gtk.ApplicationWindow):
    ui_file = 'window.ui'
    top_object = 'main-window'

    def __init__(self, *args, **kwargs):
        self.set_wmclass('Trifle', 'Trifle')
        self.maximize()
        self.connect('realize', self.on_show)

        self.side_toolbar = self.builder.get_object('sidetoolbar')
        self.main_toolbar = self.builder.get_object('maintoolbar')
        self.subscriptions = widgets.SubscriptionsView()
        self.items = widgets.ItemsView()
        self.item_view = widgets.ItemView()
        self.sizegroup = self.builder.get_object('side-sizegroup')
        self.paned = self.builder.get_object('paned')
        self.header = Gtk.Label('This is header')

    def on_show(self, window):
        widgets.populate_side_menubar(self.side_toolbar)
        self.side_toolbar.show_all()
        widgets.populate_main_menubar(self.main_toolbar)
        self.main_toolbar.show_all()
        self.side_toolbar.spinner.set_visible(False)
        self.paned.connect('notify::position', self.on_pos_change)

        self.item_view.set_controls(star=self.main_toolbar.star,
                                    unread=self.main_toolbar.unread)

        #main_box = self.builder.get_object('mainview-box')
        #main_box.pack_start(self.header, False, True, 0)
        #main_box.reorder_child(self.header, 0)
        #self.header.show()

        self.builder.get_object('subscriptions').add(self.subscriptions)
        self.subscriptions.show()

        self.builder.get_object('items').add(self.items)
        self.items.show()

        self.builder.get_object('item').add(self.item_view)
        self.item_view.show()

    def on_pos_change(self, paned, pos):
        self.side_toolbar.props.width_request = self.paned.props.position


class PreferencesDialog(utils.BuiltMixin, Gtk.Dialog):
    ui_file = 'preferences-dialog.ui'
    top_object = 'preferences-dialog'

    def __init__(self, *args, **kwargs):
        self.set_properties(**kwargs)
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

    def on_change(self, widget, setting):
        settings[setting] = int(widget.get_active_id())

    def on_val_change(self, adj, setting):
        settings[setting] = adj.get_value()

    def on_toggle(self, widget, setting):
        settings[setting] = widget.get_active()

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
    This dialog will ensure, that user becomes logged in by any means
    """
    ui_file = 'login-dialog.ui'
    top_object = 'login-dialog'

    def __init__(self, *args, **kwargs):
        self.set_properties(**kwargs)

        self.user_entry = self.builder.get_object('username')
        self.passwd_entry = self.builder.get_object('password')
        self.msg = Gtk.Label()
        self.builder.get_object('message').pack_start(self.msg, False, True, 0)
        self.user_entry.connect('activate', self.on_activate)
        self.passwd_entry.connect('activate', self.on_activate)
        self.connect('response', self.on_response)

    def on_response(self, dialog, r, data=None):
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

    def on_activate(self, entry, data=None):
        self.emit('response', 0)


class SubscribeDialog(utils.BuiltMixin, Gtk.Dialog):
    """
    This dialog will ensure, that user becomes logged in by any means
    """
    ui_file = 'subscribe-dialog.ui'
    top_object = 'subscribe-dialog'

    def __init__(self, *args, **kwargs):
        self.set_properties(**kwargs)

        self.url_entry = self.builder.get_object('url')
        self.url_entry.connect('activate', self.on_activate)
        self.url = None
        self.connect('response', self.on_response)

    def on_response(self, dialog, r, data=None):
        if r in (Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            # <ESC> or [Cancel] button pressed
            self.destroy()
            return
        url = self.url_entry.get_text()
        if len(url) == 0:
            return
        logger.debug('Subscribing to {0}'.format(url))
        self.url = url
        self.destroy()

    def on_activate(self, entry, data=None):
        self.emit('response', 0)
