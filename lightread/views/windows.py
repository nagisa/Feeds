from gi.repository import Gtk, WebKit
from views import widgets


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


class PreferencesDialog(Gtk.Dialog):

    def __init__(self, parent, *args, **kwargs):
        super(PreferencesDialog, self).__init__(*args, **kwargs)
        self.set_modal(True)
        self.set_transient_for(parent)
        content = self.get_content_area()

        grid_settings = {'row_spacing': 5, 'column_spacing': 5, 'margin': 10,
                         'margin_top': 0, 'margin_bottom': 0,
                         'column_homogeneous': True}

        general = Gtk.Grid(**grid_settings)
        notify = Gtk.CheckButton('Show notifications')
        general.attach(notify, 0, 0, 2, 1)
        refresh = Gtk.CheckButton('Refresh on start')
        general.attach(refresh, 0, 1, 2, 1)
        refresh_label = Gtk.Label('Refresh every')
        refresh_combo = Gtk.ComboBoxText()
        for time, label in ((0, 'Never'), (5, '5 minutes'), (10, '10 minutes'),
                     (30, '30 minutes'), (60, '1 hour')):
            refresh_combo.append(str(time), label)
        general.attach(refresh_label, 0, 2, 1, 1)
        general.attach(refresh_combo, 1, 2, 1, 1)
        content.pack_start(general, False, False, 0)

        cache = Gtk.Frame()
        label = Gtk.Label()
        label.set_markup('<b>{0}</b>'.format('Cache'))
        cache.set_label_widget(label)
        cache_grid = Gtk.Grid(**grid_settings)
        for row, label in enumerate(['Unread', 'Starred', 'Read']):
            cache_grid.attach(Gtk.Label(label + ' items'), 0, row, 1, 1)
            combo = Gtk.ComboBoxText()
            for days, text in ((0, 'Never'), (1, '1 day'), (2, '2 days'),
                         (3, '3 days'), (7, '1 week'), (14, '2 weeks'),
                         (28, '4 weeks'), (-1, 'Forever')):
                combo.append(str(days), text)
            cache_grid.attach(combo, 1, row, 1, 1)

        cache.add(cache_grid)
        content.pack_start(cache, False, False, 0)


class AboutDialog(Gtk.AboutDialog):

    def __init__(self, parent, *args, **kwargs):
        super(AboutDialog, self).__init__(*args, **kwargs)
        self.set_modal(True)
        self.set_transient_for(parent)
