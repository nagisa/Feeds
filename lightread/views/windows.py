import copy
from gi.repository import Gtk, WebKit
from lightread.models import settings
from lightread.views import widgets
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


class PreferencesDialog(Gtk.Dialog):

    def __new__(cls, *args, **kwargs):
        builder = Gtk.Builder(translation_domain='lightread')
        path = get_data_path('ui', 'lightread-preferences.ui')
        builder.add_from_file(path)
        new_obj = builder.get_object('preferences-dialog')
        new_obj.builder = builder
        for attr, value in cls.__dict__.items():
            setattr(new_obj, attr, value)
        # Call __init__, somewhy it doesn't do so automatically.
        new_obj.__init__(new_obj, *args, **kwargs)
        return new_obj

    def __init__(self, parent, *args, **kwargs):
        self.set_modal(True)
        self.set_transient_for(parent)

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

        for cb_name in ['unread-cache', 'starred-cache', 'read-cache']:
            combo = self.builder.get_object(cb_name)
            combo.append('0', _('Never'))
            setting_val = settings[cb_name]
            combo_days = [1, 2, 3, 7, 14, 28]
            if setting_val > 0 and setting_val not in combo_days:
                combo_days.append(setting_val)
            for day in sorted(combo_days):
                label = N_('{0} day', '{0} days', day).format(day)
                combo.append(str(day), label)
            combo.append('-1', _('Forever'))
            combo.set_active_id(str(setting_val))
            combo.connect('changed', self.on_change, cb_name)

    def on_change(widget, setting):
        settings[setting] = int(widget.get_active_id())

    def on_toggle(widget, setting):
        settings[setting] = widget.get_active()


class AboutDialog(Gtk.AboutDialog):

    def __new__(cls, *args, **kwargs):
        builder = Gtk.Builder(translation_domain='lightread')
        path = get_data_path('ui', 'lightread-about.ui')
        builder.add_from_file(path)
        new_obj = builder.get_object('about-dialog')
        new_obj.builder = builder
        for attr, value in cls.__dict__.items():
            setattr(new_obj, attr, value)
        # Call __init__, somewhy it doesn't do so automatically.
        new_obj.__init__(new_obj, *args, **kwargs)
        return new_obj

    def __init__(self, parent, *args, **kwargs):
        self.set_modal(True)
        self.set_transient_for(parent)
