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
                          TreeModelFilter, split_id, CONTENT_PATH,
                          SubscriptionColumn)
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
    us_sensitive = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)

    def do_add(self, toolitem):
        # Add it anyway
        Gtk.Toolbar.do_add(self, toolitem)
        # And do our thing
        name = toolitem.get_property('name')
        widget = toolitem.get_child()

        if name == 'categories':
            toolitem.bind_property('current-name', self, 'category')
        elif name == 'unread':
            widget.bind_property('active', self, 'unread',
                                 GObject.BindingFlags.BIDIRECTIONAL)
        elif name == 'star':
            widget.bind_property('active', self, 'starred',
                                 GObject.BindingFlags.BIDIRECTIONAL)
        elif name == 'title':
            self.bind_property('title', widget, 'label')
            self.bind_property('uri', widget, 'uri')
            toolitem.set_expand(True)
            widget.connect('notify::label', self.on_title_changed, toolitem)
        elif name == 'date':
            self.connect('notify::timestamp', self.on_timestamp_change, widget)
        else:
            logger.warning('Unknown widget added')
        if name in ('unread', 'star',):
            self.bind_property('us_sensitive', widget, 'sensitive')

    def on_timestamp_change(self, toolbar, param, label):
        time = datetime.datetime.fromtimestamp(self.timestamp)
        label.set_property('label', time.strftime('%x %X'))

    def on_title_changed(self, linkb, param, toolitem):
        linkb.get_child().set_property('ellipsize', Pango.EllipsizeMode.END)
        toolitem.show()


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
        self.connect('context-menu', self.on_ctx_menu)

        # Load base template
        template_path = get_data_path('ui', 'feedview', 'template.html')
        self.load_uri('file://' + template_path)

    def on_show(self, *args):
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

    def on_style(self, *args):
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

    def on_font(self, *args):
        family, size = parse_font(self.font)
        self.get_settings().set_properties(default_font_family=family,
                                           default_font_size=size)

    def on_monospace(self, *args):
        family, size = parse_font(self.monospace)
        self.get_settings().set_properties(default_monospace_font_size=size,
                                           monospace_font_family=family)

    def on_item_change(self, *args):
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

    def on_ctx_menu(self, view, menu, hit_test, kbd):
        # Very hackish solution, there should be a better way!
        ht_ctx = hit_test.get_property('context')
        btn, time = 0, Gtk.get_current_event_time()
        items = menu.get_children()
        image, link = ht_ctx & ht_ctx.IMAGE, ht_ctx & ht_ctx.LINK
        remove = {ht_ctx.IMAGE | ht_ctx.LINK: (1, 2, 6,), ht_ctx.LINK: (1, 2,),
                  ht_ctx.IMAGE: (1,)}
        if image or link:
            for i in remove[image | link]:
                menu.remove(items[i])
        if image or link or ht_ctx & ht_ctx.SELECTION:
            # Ain't positioning popup because it's too much pain in anus.
            menu.popup(None, None, None, None, btn, time)

    def on_inspector(self, insp, view):
        insp_view = WebKit.WebView()
        insp_win = Gtk.Window()
        insp_win.add(insp_view)
        insp_win.resize(800, 400)
        insp_win.show_all()
        insp_win.present()
        return insp_view

    def on_hovering_over_link(self, view, title, uri, data=None):
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


class SubscriptionsView(Gtk.TreeView):
    def __init__(self, *args, **kwargs):
        super(SubscriptionsView, self).__init__(*args, **kwargs)

        column = Gtk.TreeViewColumn("Subscription")
        icon_renderer = Gtk.CellRendererPixbuf()
        column.pack_start(icon_renderer, False)
        column.add_attribute(icon_renderer, 'pixbuf', SubscriptionColumn.ICON)

        title_renderer = Gtk.CellRendererText(ellipsize_set=True,
                                            ellipsize=Pango.EllipsizeMode.END)
        column.pack_start(title_renderer, True)
        column.add_attribute(title_renderer, 'text', SubscriptionColumn.NAME)

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
        super(ItemsView, self).__init__(*args, **kwargs)
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

    def category_change(self, w, gprop):
        # Still not initialized fully.
        if not self.main_model:
            return

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

        # Should be at the end of the function
        # Or rather there should be no selection when this is called.
        self.main_model.unforce_all()

    def subscription_change(self, w, gprop):
        # Still not initialized fully.
        if not self.main_model:
            return

        if self.is_label:
            key, subscr = ItemsColumn.LBL_ID, self.subscription
        else:
            key = ItemsColumn.SUB_ID
            subscr = split_id(self.subscription)[1]

        visible_func = lambda m, i, d: m[i][d[0]] == d[1]
        filt = TreeModelFilter(child_model=self.category_model)
        filt.set_visible_func(visible_func, (key, subscr))
        self.set_model(filt)

        # Should be at the end of the function
        # Or rather there should be no selection when this is called.
        self.main_model.unforce_all()


GObject.type_register(MainToolbar)
GObject.type_register(ItemView)
GObject.type_register(SubscriptionsView)
GObject.type_register(ItemsView)
