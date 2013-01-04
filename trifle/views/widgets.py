# -*- coding: utf-8 -*-
from gettext import gettext as _
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import WebKit
import base64
import datetime
import os

from trifle.arguments import arguments
from trifle.utils import (get_data_path, logger, parse_font, ItemsColumn,
                          TreeModelFilter, split_id, CONTENT_PATH)
from trifle import models

from trifle.views import toolitems
from trifle.views.itemcell import ItemCellRenderer


class MainToolbar(Gtk.Toolbar):
    timestamp = GObject.property(type=GObject.TYPE_UINT64)
    title = GObject.property(type=GObject.TYPE_STRING)
    uri = GObject.property(type=GObject.TYPE_STRING)
    category = GObject.property(type=GObject.TYPE_STRING)
    unread = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    starred = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)

    def __init__(self, *args, **kwargs):
        super(MainToolbar, self).__init__(*args, show_arrow=False,
                                         toolbar_style=Gtk.ToolbarStyle.TEXT,
                                         icon_size=2,
                                         **kwargs)
        self.get_style_context().add_class('menubar')
        self.get_style_context().add_class('trifle-toolbar')

        # Category buttons [All|Unread|Starred]
        ids = ['reading-list', 'unread', 'starred']
        buttons = [Gtk.RadioButton(_('All'), draw_indicator=False),
                   Gtk.RadioButton(_('Unread'), draw_indicator=False),
                   Gtk.RadioButton(_('Starred'), draw_indicator=False)]
        categories = toolitems.ToolLinkedButtons(margin_right=5)
        for k, b in zip(ids, buttons): categories.add_button(k, b)

        # Item status buttons [Make unread] [Make starred]
        unread = Gtk.ToggleToolButton(label=_('Mark as unread'),
                                           margin_right=5)

        starred = Gtk.ToggleToolButton(label=_('Toggle star'),
                                            margin_right=5)

        # Item title button
        args = {'margin_right': 5, 'no_show_all': True,
                'halign': Gtk.Align.CENTER}
        self.title_button = toolitems.ToolLinkButton(**args)
        self.title_button.set_expand(True)

        # Item date label
        self.date_label = toolitems.ToolLabel()

        self.insert(categories, -1)
        self.insert(unread, -1)
        self.insert(starred, -1)
        self.insert(self.title_button, -1)
        self.insert(self.date_label, -1)

        categories.bind_property('current-id', self, 'category')
        unread.bind_property('active', self, 'unread',
                                  GObject.BindingFlags.BIDIRECTIONAL)
        starred.bind_property('active', self, 'starred',
                                   GObject.BindingFlags.BIDIRECTIONAL)
        self.bind_property('title', self.title_button, 'label')
        self.bind_property('uri', self.title_button, 'uri')
        self.connect('notify::timestamp', self.on_timestamp_change)
        self.connect('notify::title', self.on_title_change)

    @staticmethod
    def on_timestamp_change(self, param):
        time = datetime.datetime.fromtimestamp(self.timestamp)
        self.date_label.label.set_text(time.strftime('%x %X'))

    @staticmethod
    def on_title_change(self, param):
        label = self.title_button.get_child().get_child()
        label.set_property('ellipsize', Pango.EllipsizeMode.END)
        self.title_button.show()


class ItemView(WebKit.WebView):
    item_id = GObject.property(type=object)
    font = GObject.property(type=GObject.TYPE_STRING)
    monospace = GObject.property(type=GObject.TYPE_STRING)
    load_cancellable = GObject.property(type=Gio.Cancellable)

    def __init__(self, *args, **kwargs):
        # TODO: Change to DOCUMENT_VIEWER after we start caching remote
        # resources at item processing stage
        WebKit.set_cache_model(WebKit.CacheModel.DOCUMENT_BROWSER)
        WebKit.get_default_session().set_property('max-conns-per-host', 8)

        settings = WebKit.WebSettings()
        settings.set_properties(**{
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
        })
        super(ItemView, self).__init__(*args, settings=settings, **kwargs)

        self.connect('show', self.on_show)
        self.connect('style-updated', self.on_style)
        self.connect('notify::item-id', self.on_item_change)
        self.connect('console-message', self.on_console_message)

        # Load base template
        template_path = get_data_path('ui', 'feedview', 'template.html')
        self.load_uri('file://' + template_path)

    @staticmethod
    def on_show(self):
        self.connect('navigation-policy-decision-requested', self.on_navigate)
        self.connect('notify::font', self.on_font)
        self.connect('notify::monospace', self.on_monospace)
        self.connect('hovering-over-link', self.on_hovering_over_link)

        GET = Gio.SettingsBindFlags.GET
        for s, p in (('document', 'font'), ('monospace', 'monospace')):
            models.settings.desktop.bind(s + '-font-name', self, p, GET)

        if arguments.devtools:
            inspector = self.get_inspector()
            inspector.connect('inspect-web-view', self.on_inspector)
            inspector.inspect_coordinates(0, 0)

    @staticmethod
    def on_style(self):
        ctx = self.get_style_context()
        text = ctx.get_color(Gtk.StateFlags.NORMAL).to_string()
        bg = ctx.get_background_color(Gtk.StateFlags.NORMAL).to_string()
        succ, link = ctx.lookup_color('link_color')
        link = link.to_string() if succ else '#4a90d9'
        font_descr = self.get_pango_context().get_font_description()
        font_size = font_descr.get_size() / Pango.SCALE
        style = '''html, body {{color: {0}; background: {1};}}
                   *:link {{ color: {2};
                   }}'''.format(text, bg, link, font_size)

        encoded = base64.b64encode(bytes(style, 'utf-8'))
        uri = 'data:text/css;charset=utf-8;base64,' + encoded.decode('ascii')
        dom = self.get_dom_document()
        dom.get_element_by_id('trifle_userstyle').set_href(uri)

    @staticmethod
    def on_font(self, gprop):
        family, size = parse_font(self.font)
        self.get_settings().set_properties(default_font_family=family,
                                           default_font_size=size)

    @staticmethod
    def on_monospace(self, gprop):
        family, size = parse_font(self.monospace)
        self.get_settings().set_properties(default_monospace_font_size=size,
                                           monospace_font_family=family)

    @staticmethod
    def on_item_change(self, param):
        if self.load_cancellable is not None:
            self.load_cancellable.cancel()
        self.load_cancellable = Gio.Cancellable()

        fpath = os.path.join(CONTENT_PATH, str(self.item_id))
        f = Gio.File.new_for_path(fpath)
        f.load_contents_async(self.load_cancellable, self.on_content_loaded,
                              None)

    def on_content_loaded(self, f, result, data):
        try:
            content = f.load_contents_finish(result)[1].decode('utf-8')
        except GLib.GError as e:
            if e.code == GLib.FileError.AGAIN: # Cancelled
                return
            else:
                raise

        # Scroll to (0, 0)
        self.get_hadjustment().set_value(0)
        self.get_vadjustment().set_value(0)
        # Set new data
        dom = self.get_dom_document()
        dom.get_element_by_id('trifle_content').set_inner_html(content)
        self.show()

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
        policy.ignore()
        uri = action.get_original_uri()
        if frame is not self.get_main_frame():
            return True
        elif uri.startswith('file://'):
            return False
        elif not Gio.AppInfo.launch_default_for_uri(uri, None):
            logger.error('System could not open {0}'.format(uri))
        return True

    @staticmethod
    def on_console_message(self, message, line, source):
        logger.debug(message)
        return True

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
        super(SubscriptionsView, self).__init__(*args, **kwargs)
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

#         self.connect('popup-menu', SubscriptionsView.on_popup_menu)
#         self.connect('button-press-event', SubscriptionsView.on_button_press)

    def on_cat_change(self, treeview):
        self.get_selection().unselect_all()

#     def on_popup_menu(self, event=None):
#         if event is not None:
#             btn, time = event.button, event.time
#             path = self.get_path_at_pos(*event.get_coords())[0]
#             itr = self.store.get_iter(path)
#         else:
#             btn, time = 0, Gtk.get_current_event_time()
#             itr = self.get_selection().get_selected()[1]
#             path = self.store.get_path(itr)
#
#         menu = Gtk.Menu()
#         labels = self.store.get_item_labels(itr)
#         if labels is not None:
#             for _id, label in labels.items():
#                 item = Gtk.CheckMenuItem(label=label[0], active=label[1])
#                 item.connect('toggled', self.on_label_change, (itr, _id))
#                 menu.append(item)
#             # Now we won't show menu if there's no labels added into it.
#             menu.attach_to_widget(self, None)
#             menu.show_all()
#             menu.popup(None, None, None, None, btn, time);
#         return True
#
#     def on_button_press(self, event):
#         if event.button == Gdk.BUTTON_SECONDARY \
#            and event.type == Gdk.EventType.BUTTON_PRESS:
#                return self.on_popup_menu(event)
#
#     def on_label_change(self, item, data):
#         window = self.get_toplevel()
#         application = window.get_application()
#         login_view = application.login_view
#         sync = models.synchronizers.Subscriptions(auth=login_view.model)
#         callback = lambda *a: sync.set_item_label(self.store[data[0]][:],
#                                                   data[1], item.get_active())
#         utils.connect_once(login_view, 'logged-in', callback)
#         login_view.set_transient_for(window)
#         login_view.ensure_login()
#         sync.connect('label-set', lambda *x: application.on_sync(None))


class ItemsView(Gtk.TreeView):
    category = GObject.property(type=GObject.TYPE_STRING)
    subscription = GObject.property(type=GObject.TYPE_STRING)
    is_label = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)

    main_model = GObject.property(type=models.feeds.Store, default=None)
    category_model = GObject.property(type=GObject.Object, default=None)

    def __init__(self, *args, **kwargs):
        super(ItemsView, self).__init__(None, *args, **kwargs)

        self.set_properties(headers_visible=False, fixed_height_mode=True,
                            search_column=ItemsColumn.TITLE,
                            main_model=models.feeds.Store())
        self.get_style_context().add_class('trifle-items-view')

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer)
        column.set_attributes(renderer,
                              title=ItemsColumn.TITLE,
                              summary=ItemsColumn.SUMMARY,
                              time=ItemsColumn.TIMESTAMP,
                              unread=ItemsColumn.UNREAD,
                              source=ItemsColumn.SUB_URI,
                              source_title=ItemsColumn.SUB_TITLE)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.append_column(column)

        self.connect('notify::category', self.category_change)
        self.connect('notify::subscription', self.subscription_change)
        self.connect('notify::category', self.either_change)
        self.connect('notify::subscription', self.either_change)

    def either_change(self, w, gprop):
        self.main_model.unforce_all()

    def category_change(self, w, gprop):
        if self.category in ('unread', 'starred'):
            if self.category == 'unread':
                cat_col = ItemsColumn.UNREAD
            else:
                cat_col = ItemsColumn.STARRED
            visible_col = ItemsColumn.FORCE_VISIBLE
            visible_func = lambda m, i, d: m[i][cat_col] or m[i][visible_col]
            filt = TreeModelFilter(child_model=self.main_model)
            filt.set_visible_func(visible_func)
            self.set_model(filt)
            self.category_model = filt
        else:
            self.set_model(self.main_model)
            self.category_model = self.main_model

    def subscription_change(self, w, gprop):
        if self.is_label:
            key, subscr = ItemsColumn.LBL_ID, self.subscription
        else:
            key = ItemsColumn.SUB_ID
            subscr = split_id(self.subscription)[1]

        visible_func = lambda m, i, d: m[i][d[0]] == d[1]
        filt = TreeModelFilter(child_model=self.category_model)
        filt.set_visible_func(visible_func, (key, subscr))
        self.set_model(filt)

GObject.type_register(MainToolbar)
GObject.type_register(ItemView)
GObject.type_register(CategoriesView)
GObject.type_register(SubscriptionsView)
GObject.type_register(ItemsView)
