# -*- coding: utf-8 -*-
from gi.repository import Gtk, WebKit, Pango, PangoCairo, Gdk, GObject, Gio
import datetime

from arguments import arguments
from models.utils import escape
from utils import get_data_path, _, logger
from views import utils
import models


def populate_side_menubar(toolbar):
    stock_toolbutton = Gtk.ToolButton.new_from_stock

    toolbar.spinner = ToolbarSpinner(margin_right=5)
    toolbar.insert(toolbar.spinner, -1)

    toolbar.combobox = ToolbarCategories(margin_right=5)
    toolbar.insert(toolbar.combobox, -1)

    toolbar.refresh = stock_toolbutton(Gtk.STOCK_REFRESH)
    toolbar.insert(toolbar.refresh, -1)

    toolbar.subscribe = stock_toolbutton(Gtk.STOCK_ADD)
    # toolbar.subscribe.set_expand(True)
    # toolbar.subscribe.set_halign(Gtk.Align.END)
    toolbar.insert(toolbar.subscribe, -1)

    toolbar.mark_all = stock_toolbutton(Gtk.STOCK_APPLY)
    toolbar.mark_all.set_properties(halign=Gtk.Align.END)
    toolbar.insert(toolbar.mark_all, -1)

    for item in (toolbar.refresh, toolbar.subscribe, toolbar.mark_all):
        item.set_property('margin-right', 5)


class MainToolbar(Gtk.Toolbar):
    timestamp = GObject.property(type=GObject.TYPE_UINT64)
    title = GObject.property(type=str)
    uri = GObject.property(type=str)

    def __init__(self, *args, **kwargs):
        super(MainToolbar, self).__init__(*args, show_arrow=False,
                                         toolbar_style=Gtk.ToolbarStyle.TEXT,
                                         icon_size=2,
                                         **kwargs)
        self.get_style_context().add_class('primary-toolbar')

        self.unread = Gtk.ToggleToolButton(label=_('Unread'), margin_right=5)
        self.starred = Gtk.ToggleToolButton(label=_('Starred'), margin_right=5)

        self.title_label = Gtk.Label(ellipsize=Pango.EllipsizeMode.END)
        self.title_button = Gtk.ToolButton(margin_right=5, no_show_all=True,
                                           halign=Gtk.Align.CENTER,
                                           label_widget=self.title_label)
        self.title_button.set_expand(True)
        self.title_button.set_size_request(100, -1)

        self.date_label = ToolbarLabel(margin_right=5)
        self.date_label.label.set_property('justify', Gtk.Justification.CENTER)

        self.insert(self.unread, -1)
        self.insert(self.starred, -1)
        self.insert(self.title_button, -1)
        self.insert(self.date_label, -1)

        self.connect('notify::timestamp', self.on_timestamp_change)
        self.connect('notify::title', self.on_title_change)
        self.connect('notify::url', self.on_title_change)
        self.title_button.connect('clicked', self.on_link)

    @staticmethod
    def on_author_change(self, param):
        return
        self.author_label.set_text(self.author)

    @staticmethod
    def on_timestamp_change(self, param):
        time = datetime.datetime.fromtimestamp(self.timestamp)
        self.date_label.label.set_text(time.strftime('%x\n%X'))

    @staticmethod
    def on_title_change(self, param):
        self.title_label.set_markup('<b>{0}</b>'.format(escape(self.title)))
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_button.show()
        self.title_label.show()

    def on_link(self, button):
        if not Gio.AppInfo.launch_default_for_uri(self.uri, None):
            logger.error('System could not open {0}'.format(self.uri))

    def set_item(self, item):
        self.set_properties(timestamp=item.time, title=item.title,
                            uri=item.href)
        self.starred.set_active(item.starred)
        self.unread.set_active(False)


# NOTE: When we'll use it, port to Gtk.SearchEntry. Will also raise version
# of GTK we depend on to 3.6.
# class ToolbarSearch(Gtk.ToolItem):
#
#     def __init__(self, *args, **kwargs):
#         super(ToolbarSearch, self).__init__(*args, **kwargs)
#         self.entry = Gtk.Entry(hexpand=True, halign=Gtk.Align.FILL)
#         self.set_unread_count(0)
#         self.add(self.entry)
#
#     def set_unread_count(self, items):
#         self.entry.set_placeholder_text(_('Search {0} items').format(items))


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
        content = self.item.read_content(self.item.item_id)
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
        if treeview.in_destruction() or treeview.reloading:
            return
        selection = treeview.get_selection().get_selected()
        item = selection[0].get_value(selection[1], 0)
        # We don't have anything to do if same item is being loaded
        if item is self.item:
            return None
        self.item = item
        if self.item.unread: # Set it to read
            self.item.set_read()

    def on_star(self, button):
        if button.get_active():
            self.item.set_star(True)
        else:
            self.item.set_star(False)

    def on_keep_unread(self, button):
        if button.get_active():
            self.item.set_keep_unread(True)
        else:
            self.item.set_keep_unread(False)


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
        from views import app
        app.window.side_toolbar.spinner.show()
        app.ensure_login(lambda: \
            self.store.set_item_label(data[0], data[1], item.get_active()))
        def sync_done(*args):
            app.window.side_toolbar.spinner.hide()
        utils.connect_once(self.store, 'sync-done', sync_done)

    def sync(self, callback=None):
        logger.debug('Starting subscriptions\' sync')
        self.store.sync()
        if callback is not None:
            utils.connect_once(self.store, 'sync-done', callback)


class ItemsView(Gtk.TreeView):
    def __init__(self, *args, **kwargs):
        self.reloading = False
        self.store = models.feeds.FilteredItems()
        super(ItemsView, self).__init__(self.store, *args, **kwargs)
        self.set_properties(headers_visible=False,
                            enable_grid_lines=Gtk.TreeViewGridLines.HORIZONTAL)

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer, item=0)
        self.append_column(column)
        self.connect('realize', self.on_realize)

    def sync(self, callback=None):
        logger.debug('Starting items\' sync')
        self.store.sync()
        if callback is not None:
            utils.connect_once(self.store, 'sync-done', callback)

    @staticmethod
    def on_realize(self):
        self.store.load_ids(self.store.category_ids('reading-list'))

    def on_filter_change(self, treeview):
        if treeview.in_destruction():
            return
        model, selection = treeview.get_selection().get_selected()
        self.reloading = True
        if selection is not None:
            row = model[selection]
            self.store.load_ids(self.store.filter_ids(row[0], row[1]))
        else:
            logger.warning('Cannot set filter, there\'s no selection')
        self.reloading = False

    def on_cat_change(self, combobox):
        category = combobox.get_active_id()
        self.reloading = True
        if category is not None:
            self.store.load_ids(self.store.category_ids(category))
        self.reloading = False

    def on_all_read(self, button):
        for item in self.store:
            if item[0].unread:
                item[0].set_read()


class ItemCellRenderer(Gtk.CellRenderer):
    item = GObject.property(type=models.feeds.FeedItem)
    markup = {'date': '<span color="{color}" size="9216">{text}</span>',
              'site': '<span color="{color}" size="9216">{text}</span>',
              'title': '<span color="{color}" size="10240" '
                       'weight="{weight}">{text}</span>',
              'summary': '<span color="{color}" size="9216">{text}</span>',
              'dummy': '<span size="{size}">{text}</span>'}
    height = None
    padding = 2
    line_spacing = 2
    icon_size = 16
    sizes = {'date': 9216, 'site': 9216, 'title': 10240, 'summary': 9216}
    heights = [0, 0, 0]

    def __init__(self, *args, **kwargs):
        super(ItemCellRenderer, self).__init__(*args, **kwargs)
        self.left_padding = 0 # Replaced later by render_icon
        self.state = Gtk.StateFlags.FOCUSED

    def do_get_preferred_height(self, view):
        if self.height is None:
            layout = view.create_pango_layout('Gg')
            mapping = {'size': max(self.sizes['date'], self.sizes['site']),
                       'text': 'Gg'}
            layout.set_markup(self.markup['dummy'].format_map(mapping))
            self.heights[0] = max(self.icon_size,
                                  layout.get_pixel_extents()[1].height)
            mapping['size'] = self.sizes['title']
            layout.set_markup(self.markup['dummy'].format_map(mapping))
            self.heights[1] = layout.get_pixel_extents()[1].height
            mapping['size'] = self.sizes['summary']
            layout.set_markup(self.markup['dummy'].format_map(mapping))
            self.heights[2] = layout.get_pixel_extents()[1].height
            self.heights = [h + self.line_spacing for h in self.heights]
            ItemCellRenderer.height = self.padding * 2 + sum(self.heights)
        return self.height, self.height

    # Any of render functions should not modify self.* in any way
    def do_render(self, context, view, bg_area, cell_area, flags):
        if flags & Gtk.CellRendererState.FOCUSED:
            self.state = Gtk.StateFlags.SELECTED
        else:
            self.state = Gtk.StateFlags.NORMAL

        y, x = cell_area.y + self.padding, cell_area.x + self.padding
        style = view.get_style_context()

        # First line containing icon, subscription title and date
        icon_w, icon_h = self.render_icon(y, x, context)
        date_w, date_h = self.render_date(y, icon_h, view, context, cell_area,
                                          style)
        site_w = cell_area.width - date_w - self.line_spacing * 2 - icon_w - x
        self.render_site(y, x + icon_w + self.line_spacing, site_w, icon_h,
                         view, context, cell_area, style)

        # This  is width for both title and summary
        ts_w = cell_area.width - self.padding * 2
        # Second line, title of item
        y += self.line_spacing + self.heights[1]
        title_w, title_h = self.render_title(y, x, ts_w, view, context, style)

        # Third line, summary
        y += self.line_spacing + self.heights[2]
        summ_w, summ_h = self.render_summary(y, x, ts_w, view, context, style)

    def render_icon(self, y, x, context=None):
        if self.item is None:
            return 16, 16 # Icons will always be 16x16 (But there may be none)

        icon = self.item.icon
        if icon is not None:
            Gdk.cairo_set_source_pixbuf(context, icon, x, y)
            context.paint()
            return icon.get_width(), icon.get_height()
        return 0, 0

    def render_date(self, y, icon_h, view, context, cell_area, style):
        if self.item is None:
            return 0, 0

        # We want to use theme colors for time string. So in Adwaita text
        # looks blue, and in Ubuntu default theme – orange.
        if self.state == Gtk.StateFlags.NORMAL:
            color = style.get_background_color(Gtk.StateFlags.SELECTED)
            normal = style.get_background_color(self.state)
            # In Ambiance and handful other themes we get a trasparent color
            if color.alpha < 0.01 or color == normal:
                color = style.get_color(self.state)
        else:
            color = style.get_color(Gtk.StateFlags.SELECTED)

        text = utils.time_ago(self.item.time)
        markup = self.markup['date'].format(text=text,
                                            color=utils.hexcolor(color))

        layout = view.create_pango_layout(text)
        layout.set_markup(markup)
        layout.set_alignment(Pango.Alignment.RIGHT)

        rect = layout.get_pixel_extents()[1]
        y += (icon_h - rect.height) / 2
        x = cell_area.width - rect.width - rect.x - self.padding
        context.move_to(x, y)
        PangoCairo.show_layout(context, layout)
        return rect.width, rect.height

    def render_site(self, y, x, width, icon_h, view, context, cell_area,
                    style):
        if self.item is None:
            return 0, 0

        color = utils.hexcolor(style.get_color(self.state))
        text = self.item.site
        markup = self.markup['site'].format(text=escape(text), color=color)

        layout = view.create_pango_layout(text)
        layout.set_markup(markup)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_width(width * Pango.SCALE)
        rect = layout.get_pixel_extents()[1]
        y += (icon_h - rect.height) / 2
        context.move_to(x, y)
        PangoCairo.show_layout(context, layout)
        return rect.width, rect.height

    def render_title(self, y, x, width, view, context, style):
        if self.item is None:
            return 0, 0

        text = self.item.title
        weight = 'bold' if self.item.unread else 'normal'
        color = utils.hexcolor(style.get_color(self.state))
        markup = self.markup['title'].format(text=escape(text), color=color,
                                             weight=weight)

        layout = view.create_pango_layout(text)
        layout.set_markup(markup)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_width(width * Pango.SCALE)
        context.move_to(x, y)
        PangoCairo.show_layout(context, layout)
        rect = layout.get_pixel_extents()[1]
        return rect.width, rect.height

    def render_summary(self, y, x, width, view, context, style):
        if self.item is None:
            return 0, 0

        text = self.item.summary
        color = utils.hexcolor(style.get_color(self.state))
        markup = self.markup['summary'].format(text=escape(text), color=color)

        layout = view.create_pango_layout(text)
        layout.set_markup(markup)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_width(width * Pango.SCALE)
        rect = layout.get_pixel_extents()[1]
        context.move_to(x, y)
        PangoCairo.show_layout(context, layout)
        return rect.width, rect.height
