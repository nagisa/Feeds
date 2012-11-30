# -*- coding: utf-8 -*-
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import WebKit
import datetime

from trifle.arguments import arguments
from trifle.utils import get_data_path, _, logger
from trifle import models

from trifle.views import utils
from trifle.views.itemcell import ItemCellRenderer


class MainToolbar(Gtk.Toolbar):
    timestamp = GObject.property(type=GObject.TYPE_UINT64)
    title = GObject.property(type=str)
    uri = GObject.property(type=str)
    category = GObject.property(type=str)

    def __init__(self, *args, **kwargs):
        super(MainToolbar, self).__init__(*args, show_arrow=False,
                                         toolbar_style=Gtk.ToolbarStyle.TEXT,
                                         icon_size=2,
                                         **kwargs)
        self.get_style_context().add_class('menubar')
        self.get_style_context().add_class('trifle-toolbar')

        # Category selectors [All|Unread|Starred]
        self.category_buttons = (
            ('reading-list', Gtk.RadioButton(_('All'), draw_indicator=False)),
            ('unread', Gtk.RadioButton(_('Unread'), draw_indicator=False)),
            ('starred', Gtk.RadioButton(_('Starred'), draw_indicator=False)),
        )
        button_box = Gtk.Box()
        button_box.get_style_context().add_class('linked')
        categories = Gtk.ToolItem(margin_right=5)
        categories.add(button_box)
        for key, item in self.category_buttons:
            button_box.pack_start(item, False, True, 0)
            item.connect('toggled', self.on_category_change)
            if item is not self.category_buttons[0][1]:
                item.set_property('group', self.category_buttons[0][1])

        # Item status buttons [Make unread] [Make starred]
        self.unread = Gtk.ToggleToolButton(label=_('Make unread'),
                                           margin_right=5)
        self.starred = Gtk.ToggleToolButton(label=_('Make starred'),
                                            margin_right=5)

        # Item title button
        self.title_label = Gtk.Label(ellipsize=Pango.EllipsizeMode.END)
        self.title_button = Gtk.ToolItem(margin_right=5, no_show_all=True,
                                           halign=Gtk.Align.CENTER)
        self.title_link = Gtk.LinkButton('127.0.0.1')
        self.title_link.show()
        self.title_button.add(self.title_link)
        self.title_button.set_expand(True)
        self.title_button.set_size_request(100, -1)

        # Item date label
        self.date_label = ToolbarLabel(margin_right=5)
        self.date_label.label.set_property('justify', Gtk.Justification.CENTER)

        self.insert(categories, -1)
        self.insert(self.unread, -1)
        self.insert(self.starred, -1)
        self.insert(self.title_button, -1)
        self.insert(self.date_label, -1)

        self.connect('notify::timestamp', self.on_timestamp_change)
        self.connect('notify::title', self.on_title_change)
        self.connect('notify::url', self.on_title_change)

    @staticmethod
    def on_timestamp_change(self, param):
        time = datetime.datetime.fromtimestamp(self.timestamp)
        self.date_label.label.set_text(time.strftime('%x %X'))

    @staticmethod
    def on_title_change(self, param):
        self.title_link.set_properties(label=self.title, uri=self.uri)
        self.title_link.get_child().set_property('ellipsize',
                                                 Pango.EllipsizeMode.END)
        self.title_button.show()

    def on_category_change(self, button):
        if not button.get_active():
            return
        for key, item in self.category_buttons:
            if item == button:
                self.category = key
                return

    def set_item(self, item):
        self.set_properties(timestamp=item.time, title=item.title,
                            uri=item.href)
        self.starred.set_active(item.starred)
        self.unread.set_active(False)



class ToolbarSpinner(Gtk.ToolItem):
    def __init__(self, *args, **kwargs):
        super(ToolbarSpinner, self).__init__(*args, **kwargs)
        self.spinner = Gtk.Spinner(active=True)
        self.add(self.spinner)
        self.show_count = 0

    def show(self):
        self.show_count += 1
        self.spinner.show_all()
        super(ToolbarSpinner, self).show()

    def hide(self):
        self.show_count -= 1
        if self.show_count == 0:
            super(ToolbarSpinner, self).hide()


class ToolbarComboBoxText(Gtk.ToolItem):
    def __init__(self, *args, **kwargs):
        super(ToolbarComboBoxText, self).__init__(*args, **kwargs)
        self.child = Gtk.ComboBoxText()
        self.add(self.child)


class ToolbarCategories(ToolbarComboBoxText):
    def __init__(self, *args, **kwargs):
        super(ToolbarCategories, self).__init__(*args, **kwargs)
        self.child.append('reading-list', _('All items'))
        self.child.append('unread', _('Unread items'))
        self.child.append('starred', _('Starred items'))


class ToolbarLabel(Gtk.ToolItem):
    def __init__(self, *args, **kwargs):
        super(ToolbarLabel, self).__init__(*args, **kwargs)
        self.label = Gtk.Label()
        self.add(self.label)


class ItemView(WebKit.WebView):
    item = GObject.property(type=GObject.Object)

    settings_props = {
        # These three saves us ~25MiB of residental memory
        'enable_scripts': False, 'enable_plugins': False,
        'enable_java_applet': False,
        # We already have most files cached and load locally
        'enable_page_cache': False, 'enable_dns_prefetching': False,
        'enable_private_browsing': True,
        # We don't use any of these features
        'enable_html5_database': False, 'enable_html5_local_storage': False,
        'enable_offline_web_application_cache': False,
        'enable_xss_auditor': False, 'resizable_text_areas': False,
        # Need this one of usability reasons.
        'enable_default_context_menu': False,
        # Enable in case developer tools are needed
        'enable_developer_extras': arguments.devtools
    }

    def __init__(self, *args, **kwargs):
        # TODO: Change to DOCUMENT_VIEWER after we start caching remote
        # resources at item processing stage
        WebKit.set_cache_model(WebKit.CacheModel.DOCUMENT_BROWSER)
        WebKit.get_default_session().set_property('max-conns-per-host', 8)

        super(ItemView, self).__init__(*args, **kwargs)
        self.connect('navigation-policy-decision-requested', self.on_navigate)
        self.connect('console-message', self.on_console_message)
        self.connect('hovering-over-link', self.on_hovering_over_link)
        self.connect('notify::item', self.on_item_change)

        self.settings = WebKit.WebSettings()
        self.settings.set_properties(**self.settings_props)
        self.set_settings(self.settings)
        if arguments.devtools:
            insp = self.get_inspector()
            insp.connect('inspect-web-view', self.on_inspector)
            insp.inspect_coordinates(0, 0)

        # Load base template
        template_path = get_data_path('ui', 'feedview', 'template.html')
        self.load_uri('file://' + template_path)

    @staticmethod
    def on_item_change(self, param):
        # Scroll to (0, 0)
        self.get_hadjustment().set_value(0)
        self.get_vadjustment().set_value(0)
        # Set new data
        dom = self.get_dom_document()
        content = self.item.content
        dom.get_element_by_id('trifle_content').set_inner_html(content)
        # IFrame repacement
        iframes = dom.get_elements_by_tag_name('iframe')
        while iframes.item(0) is not None:
            iframe = iframes.item(0)
            uri = iframe.get_src()
            repl = dom.get_element_by_id('trifle_iframe').clone_node(True)
            repl.set_href(uri)
            repl.set_inner_text(uri)
            iframe.get_parent_node().replace_child(repl, iframe)

    def on_inspector(self, insp, view):
        insp_view = WebKit.WebView()
        insp_win = Gtk.Window()
        insp_win.add(insp_view)
        insp_win.resize(800, 400)
        insp_win.show_all()
        insp_win.present()
        return insp_view

    @staticmethod
    def on_hovering_over_link(self, title, uri, data=None):
        dom = self.get_dom_document()
        statusbar = dom.get_element_by_id('trifle_statusbar')
        if uri is None:
            statusbar.get_class_list().remove('visible')
        else:
            statusbar.get_class_list().add('visible')
            statusbar.set_inner_text(uri)

    @staticmethod
    def on_navigate(self, frame, request, action, policy):
        if frame is not self.get_main_frame():
            policy.ignore()
            return True
        uri = action.get_original_uri()
        if not uri.startswith('file://'):
            if not Gio.AppInfo.launch_default_for_uri(uri, None):
                logger.error('System could not open {0}'.format(uri))
            policy.ignore()
            return True
        return False

    @staticmethod
    def on_console_message(self, message, line, source):
        logger.debug(message)
        return True

    def on_change(self, treeview):
        if treeview.in_destruction():
            return
        selection = treeview.get_selection().get_selected()
        if selection[0] is None or selection[1] is None:
            return
        item = selection[0].get_value(selection[1], 0)
        # We don't have anything to do if same item is being loaded
        if item is self.item:
            return None
        self.item = item
        self.item.unread = False

    def on_star(self, button):
        self.item.starred = button.get_active()

    def on_keep_unread(self, button):
        self.item.unread = button.get_active()

class CategoriesView(Gtk.TreeView):

    def __init__(self, *args, **kwargs):
        self._store = Gtk.ListStore(str, str, str)
        super(CategoriesView, self).__init__(self._store, *args, **kwargs)
        self.set_properties(headers_visible=False)

        column = Gtk.TreeViewColumn("Categories")
        icon = Gtk.CellRendererPixbuf()
        title = Gtk.CellRendererText()
        column.pack_start(icon, False)
        column.pack_start(title, True)
        column.add_attribute(icon, "icon-name", 0)
        column.add_attribute(title, "text", 1)
        self.append_column(column)

        self.selection = self.get_selection()
        i = self.append(Gtk.STOCK_JUSTIFY_FILL, _('All items'), 'reading-list')
        self.append(Gtk.STOCK_INDEX, _('Unread'), 'unread')
        self.append(Gtk.STOCK_ABOUT, _('Starred'), 'starred')
        self.selection.select_iter(i)

    def append(self, icon, title, tp):
        return self._store.append((icon, title, tp,))


class SubscriptionsView(Gtk.TreeView):

    def __init__(self, *args, **kwargs):
        self.store = models.subscriptions.Subscriptions()
        super(SubscriptionsView, self).__init__(self.store, *args, **kwargs)
        self.set_properties(headers_visible=False)
        self.set_level_indentation(-12)

        column = Gtk.TreeViewColumn("Subscription")
        icon_renderer = Gtk.CellRendererPixbuf()
        title_renderer = Gtk.CellRendererText(ellipsize_set=True,
                                            ellipsize=Pango.EllipsizeMode.END)
        column.pack_start(icon_renderer, False)
        column.pack_start(title_renderer, True)
        column.add_attribute(icon_renderer, 'pixbuf', 2)
        column.add_attribute(title_renderer, 'text', 3)
        self.append_column(column)

        self.connect('realize', self.on_realize)
        self.connect('popup-menu', SubscriptionsView.on_popup_menu)
        self.connect('button-press-event', SubscriptionsView.on_button_press)

    @staticmethod
    def on_realize(self):
        self.store.update()

    def on_cat_change(self, treeview):
        self.get_selection().unselect_all()

    def on_popup_menu(self, event=None):
        if event is not None:
            btn = event.button
            time = event.time
            path = self.get_path_at_pos(*event.get_coords())[0]
            itr = self.store.get_iter(path)
        else:
            btn = 0
            time = Gtk.get_current_event_time()
            itr = self.get_selection().get_selected()[1]
            path = self.store.get_path(itr)

        menu = Gtk.Menu()
        labels = self.store.get_item_labels(itr)
        if labels is not None:
            for _id, label in labels.items():
                item = Gtk.CheckMenuItem(label=label[0], active=label[1])
                item.connect('toggled', self.on_label_change, (itr, _id))
                menu.append(item)
            # Now we won't show menu if there's no labels added into it.
            menu.attach_to_widget(self, None)
            menu.show_all()
            menu.popup(None, None, None, None, btn, time);
        return True

    def on_button_press(self, event):
        if event.button == Gdk.BUTTON_SECONDARY \
           and event.type == Gdk.EventType.BUTTON_PRESS:
               return self.on_popup_menu(event)

    def on_label_change(self, item, data):
        from trifle.views import app
        app.window.side_toolbar.spinner.show()
        app.ensure_login(lambda: \
            self.store.set_item_label(data[0], data[1], item.get_active()))
        def sync_done(*args):
            app.window.side_toolbar.spinner.hide()
        utils.connect_once(self.store, 'sync-done', sync_done)


class ItemsView(Gtk.TreeView):
    def __init__(self, *args, **kwargs):
        self.store = models.feeds.Store()
        super(ItemsView, self).__init__(None, *args, **kwargs)
        self.set_properties(headers_visible=False,
                            enable_grid_lines=Gtk.TreeViewGridLines.HORIZONTAL)
        self.get_style_context().add_class('trifle-items-view')

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer, item=0)
        self.append_column(column)
        # Needed so model is connected after filling it up
        self.remove_and_reconnect()

    def remove_and_reconnect(self):
        self.set_model(None)
        callback = lambda *x: self.set_model(self.store)
        utils.connect_once(self.store, 'load-done', callback)

    def on_filter_change(self, treeview):
        if treeview.in_destruction():
            return
        model, selection = treeview.get_selection().get_selected()
        if selection is not None:
            row = model[selection]
            if row[1] != self.store.subscription:
                self.remove_and_reconnect()
                self.store.is_feed = row[0] == 1
                self.store.subscription = row[1]

    def on_cat_change(self, obj):
        if obj.category is not None and self.store.category != obj.category:
            self.remove_and_reconnect()
            self.store.category = obj.category

    def on_all_read(self, button):
        for item in self.store:
            if item[0].unread:
                item[0].unread = False
