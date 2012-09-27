from gi.repository import Gtk


from models.auth import auth
from models.settings import settings
from views import widgets, utils
from views.notifications import notification


class ApplicationWindow(utils.BuiltMixin, Gtk.ApplicationWindow):
    ui_file = 'window.ui'
    top_object = 'main-window'

    def __init__(self, *args, **kwargs):
        self.set_wmclass('trifle', 'trifle')
        self.set_title(_('Feeds'))
        self.maximize()
        self.connect('realize', self.on_show)

    def on_show(self, window):
        feedbox = self.builder.get_object('feedview')
        self.feedview = widgets.FeedView()
        feedbox.add(self.feedview)

        leftgrid = self.builder.get_object('left-grid')
        leftgrid.get_style_context().add_class(Gtk.STYLE_CLASS_SIDEBAR)
        self.categories = widgets.CategoriesView()
        leftgrid.attach(self.categories, 0, 0, 1, 1)

        subs = self.builder.get_object('subs')
        self.subsview = widgets.SubscriptionsView()
        subs.add(self.subsview)
        subs.reset_style()

        items = self.builder.get_object('items')
        self.itemsview = widgets.ItemsView()
        items.add(self.itemsview)

        self.itemsview.show()
        self.subsview.show()
        self.categories.show()
        self.feedview.show()

        for tb in ('items-toolbar', 'sidebar-toolbar', 'feedview-toolbar',):
            toolbar = self.builder.get_object(tb)
            widgets.add_toolbar_items(toolbar, tb)
            toolbar.get_style_context().add_class(Gtk.STYLE_CLASS_MENUBAR)
            toolbar.reset_style()
            setattr(self, tb.replace('-', '_'), toolbar)


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
        self.set_properties(**kwargs)


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

    def on_response(self, r, data=None):
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