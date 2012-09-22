# -*- coding: utf-8 -*-
from gi.repository import Gtk, WebKit, Pango, PangoCairo, GdkPixbuf, Gdk, \
                          GObject, Gio
import html
import os
import collections
import datetime

from lightread.views import utils
from lightread import models
from lightread.utils import get_data_path


def add_toolbar_items(toolbar, tb_type):
    stock_toolbutton = Gtk.ToolButton.new_from_stock
    if tb_type == 'items-toolbar':
        toolbar.mark_all = stock_toolbutton(Gtk.STOCK_APPLY)
        toolbar.insert(toolbar.mark_all, -1)

        toolbar.search = ToolbarSearch(margin_left=5, halign=Gtk.Align.FILL)
        toolbar.search.set_expand(True)
        toolbar.insert(toolbar.search, -1)

    elif tb_type == 'sidebar-toolbar':
        toolbar.refresh = stock_toolbutton(Gtk.STOCK_REFRESH)
        toolbar.refresh.set_properties(margin_right=5)
        toolbar.insert(toolbar.refresh, -1)

        toolbar.spinner = ToolbarSpinner(no_show_all=True)
        toolbar.insert(toolbar.spinner, -1)

        toolbar.subscribe = stock_toolbutton(Gtk.STOCK_ADD)
        toolbar.subscribe.set_expand(True)
        toolbar.subscribe.set_halign(Gtk.Align.END)
        toolbar.insert(toolbar.subscribe, -1)

    elif tb_type == 'feedview-toolbar':
        toolbar.star = stock_toolbutton(Gtk.STOCK_YES)
        toolbar.star.set_properties(margin_right=5)
        toolbar.insert(toolbar.star, -1)

        toolbar.share = stock_toolbutton(Gtk.STOCK_REDO)
        toolbar.share.set_properties(margin_right=5)
        toolbar.insert(toolbar.share, -1)

        toolbar.preferences = stock_toolbutton(Gtk.STOCK_PREFERENCES)
        toolbar.preferences.set_halign(Gtk.Align.END)
        toolbar.preferences.set_expand(True)
        toolbar.insert(toolbar.preferences, -1)
    else:
        raise ValueError('Unknown Toolbar')
    toolbar.show_all()


class ToolbarSearch(Gtk.ToolItem):

    def __init__(self, *args, **kwargs):
        super(ToolbarSearch, self).__init__(*args, **kwargs)
        self.entry = Gtk.Entry(hexpand=True, halign=Gtk.Align.FILL)
        self.set_unread_count(0)
        self.add(self.entry)

    def set_unread_count(self, items):
        self.entry.set_placeholder_text(_('Search {0} items').format(items))


class ToolbarSpinner(Gtk.ToolItem):

    def __init__(self, *args, **kwargs):
        super(ToolbarSpinner, self).__init__(*args, **kwargs)
        self.spinner = Gtk.Spinner(active=True)
        self.add(self.spinner)

    def show(self):
        self.spinner.show_all()
        super(ToolbarSpinner, self).show()


class FeedView(WebKit.WebView):

    def __init__(self, *args, **kwargs):
        super(FeedView, self).__init__(*args, **kwargs)
        self.connect('navigation-policy-decision-requested', self.on_navigate)
        self.connect('console-message', self.on_console_message)

        self.settings = WebKit.WebSettings()
        stylesheet_path = get_data_path('ui', 'feedview', 'style.css')
        self.settings.set_properties(
            # These three saves us ~25MiB of residental memory
            enable_scripts=False, enable_plugins=False,
            enable_java_applet=False,
            # We already have most files cached and load locally
            enable_page_cache=False, enable_dns_prefetching=False,
            # Need this one of usability reasons.
            enable_default_context_menu=False,
            # Not used
            enable_html5_database=False, enable_html5_local_storage=False,
            enable_offline_web_application_cache=False,
            enable_xss_auditor=False, resizable_text_areas=False,
            # Very effectively turns off all types of cache
            enable_private_browsing=True,
            user_stylesheet_uri='file://' + stylesheet_path
        )
        self.set_settings(self.settings)

        self.load_item()

    @staticmethod
    def on_navigate(self, frame, request, action, policy):
        uri = action.get_original_uri()
        if frame.get_parent():
            logger.warning('{0} was not loaded'.format(uri))
            policy.ignore()
            return True
        elif uri.startswith('http'):
            if not Gio.AppInfo.launch_default_for_uri(uri, None):
                logger.error('System could not open {0}'.format(uri))
            policy.ignore()
            return True
        return False

    @staticmethod
    def on_console_message(self, message, line, source):
        logger.debug(message)
        return True

    def load_item(self, item=None):
        with open(get_data_path('ui', 'feedview', 'template.html'), 'r') as f:
            template = f.read()
        if item is None:
            return self.load_html_string('', 'file://')
        else:
            content = item.read_content(item.item_id)
            dt = datetime.datetime.fromtimestamp(item.time)
            s = template.format(title=item.title, content=content,
                                href=item.href, author=item.author,
                                datetime=dt)
            return self.load_html_string(s, 'file://')

    def on_change(self, treeview):
        if treeview.in_destruction() or treeview.reloading:
            return
        selection = treeview.get_selection().get_selected()
        self.load_item(selection[0].get_value(selection[1], 0))


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
        self.store = models.Subscriptions()
        super(SubscriptionsView, self).__init__(self.store, *args, **kwargs)
        self.set_properties(headers_visible=False)
        self.set_level_indentation(-12)

        self.store.connect('pre-clear', self.on_pre_clear)
        self.store.connect('sync-done', self.on_sync_done)
        self.connect('row-collapsed', SubscriptionsView.on_collapse)
        self.connect('row-expanded', SubscriptionsView.on_expand)
        self.memory = {'expanded': [], 'selection': None}
        self.selection = self.get_selection()

        column = Gtk.TreeViewColumn("Subscription")
        icon_renderer = Gtk.CellRendererPixbuf()
        title_renderer = Gtk.CellRendererText(ellipsize_set=True,
                                            ellipsize=Pango.EllipsizeMode.END)
        column.pack_start(icon_renderer, False)
        column.pack_start(title_renderer, True)
        column.add_attribute(icon_renderer, "pixbuf", 0)
        column.add_attribute(title_renderer, "text", 1)
        self.append_column(column)

    def on_pre_clear(self, *args):
        selection = self.selection.get_selected()[1]
        if selection is not None:
            self.memory['selection'] = self.store.get_path(selection)

    def on_sync_done(self, *args):
        for path in self.memory['expanded']:
            self.expand_row(path, False)
        if self.memory['selection'] is not None:
            self.selection.select_path(self.memory['selection'])

    def on_expand(self, itr, path):
        self.memory['expanded'].append(path.copy())

    def on_collapse(self, itr, path):
        self.memory['expanded'].pop(self.memory['expanded'].index(path))

    def on_cat_change(self, treeview):
        if treeview.in_destruction():
            return
        self.selection.unselect_all()

    def sync(self, callback=None):
        logger.debug('Starting subscriptions\' sync')
        self.store.sync()
        if callback is not None:
            utils.connect_once(self.store, 'sync-done', callback)


class ItemsView(Gtk.TreeView):
    def __init__(self, *args, **kwargs):
        self.reloading = False
        self.store = models.Items()
        super(ItemsView, self).__init__(self.store, *args, **kwargs)
        self.set_properties(headers_visible=False)

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer, item=0)
        self.append_column(column)
        self.store.set_sort_column_id(0, Gtk.SortType.DESCENDING)
        self.store.set_sort_func(0, models.Items.compare, None)
        self.connect('realize', self.on_realize)

    def sync(self, callback=None):
        logger.debug('Starting items\' sync')
        self.store.sync()
        if callback is not None:
            utils.connect_once(self.store, 'sync-done', callback)

    @staticmethod
    def on_realize(self):
        self.store.set_category('reading-list')

    def on_filter_change(self, treeview):
        if treeview.in_destruction():
            return
        selection = treeview.selection.get_selected()
        self.reloading = True
        self.store.set_feed_filter(selection[0].get_value(selection[1], 2))
        self.reloading = False

    def on_cat_change(self, treeview):
        if treeview.in_destruction():
            return
        selection = treeview.selection.get_selected()
        self.reloading = True
        self.store.set_category(selection[0].get_value(selection[1], 2))
        self.reloading = False

class ItemCellRenderer(Gtk.CellRenderer):
    item = GObject.property(type=models.FeedItem)
    markup = {'date': '<span color="{color}" size="9216">{text}</span>',
              'site': '<span color="{color}" size="9216">{text}</span>',
              'title': '<span color="{color}" size="10240" ' \
                       'weight="{weight}">{text}</span>',
              'summary': '<span color="{color}" size="9216">{text}</span>'}

    def __init__(self, *args, **kwargs):
        super(ItemCellRenderer, self).__init__(*args, **kwargs)
        self.summary_height = 0
        self.spacing = 4
        self.left_padding = 0 # Replaced later by render_icon
        self.height = 0
        self.state = Gtk.StateFlags.FOCUSED

    def do_render(self, ctx, widget, bg_area, cell_area, flags):
        if flags & Gtk.CellRendererState.FOCUSED:
            self.state = Gtk.StateFlags.SELECTED
        else:
            self.state = Gtk.StateFlags.NORMAL
        self.render(widget, cell_area, ctx)

    def do_get_size(self, widget, cell_area):
        if self.height == 0:
            self.render(widget, cell_area)
        return 0, 0, 0, self.height

    def render(self, widget, cell_area, ctx=None):
        offset = y = cell_area.y if cell_area is not None else self.spacing
        y += cell_area.x if cell_area is not None else self.spacing


        # Render a first line, icon, site title and date
        height = self.render_icon(widget, cell_area, ctx, y)
        width = self.render_date(widget, cell_area, ctx, y, height)
        self.render_site(widget, cell_area, ctx, y, width, height)
        y += height + int(self.spacing / 2)
        # Second and third lines
        ink = self.render_title(widget, cell_area, ctx, y)
        y += ink.height + self.spacing
        ink = self.render_summary(widget, cell_area, ctx, y)
        y += ink.height + self.spacing
        self.height = y - offset if self.height == 0 else self.height

    def render_icon(self, widget, cell_area, ctx, y):
        if self.item.icon is not None:
            if ctx is not None and cell_area is not None:
                Gdk.cairo_set_source_pixbuf(ctx, self.item.icon,
                                            cell_area.x, y)
                ctx.paint()
                self.left_padding = self.item.icon.get_width() + cell_area.x
                return self.item.icon.get_height()
        elif cell_area is not None:
            self.left_padding = cell_area.x
        else:
            self.left_padding = 0
        return 16

    def render_date(self, widget, cell_area, ctx, y, height):
        # We want to use theme colors for time string. So in Adwaita text
        # looks blue, and in Ubuntu default theme – orange.
        context = widget.get_style_context()
        if self.state == Gtk.StateFlags.NORMAL:
            color = context.get_background_color(Gtk.StateFlags.SELECTED)
        else:
            color = context.get_color(Gtk.StateFlags.SELECTED)

        # Because of bindings' limitations we have very restricted ability to
        # make attributes programmatically, so we have to parse markup.
        text = utils.time_ago(self.item.time)
        layout = widget.create_pango_layout(text)
        layout.set_markup(self.markup['date'].format(text=text,
                          color=utils.hexcolor(color)))
        layout.set_alignment(Pango.Alignment.RIGHT)

        ink, x = layout.get_pixel_extents()[0], 0
        y += int((height - ink.height) / 2)
        if ctx is not None and cell_area is not None:
            x = cell_area.width - cell_area.x - ink.width - ink.x
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, layout)
        return x

    def render_site(self, widget, cell_area, ctx, y, maxx, height):
        color = widget.get_style_context().get_color(self.state)
        layout = widget.create_pango_layout(self.item.site)
        layout.set_markup(self.markup['site'].format(text=self.item.site,
                          color=utils.hexcolor(color)))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        max_width = (maxx - self.left_padding - self.spacing)
        layout.set_width(max_width * Pango.SCALE)

        ink = layout.get_pixel_extents()[0]
        y += int((height - ink.height) / 2)
        if ctx is not None and cell_area is not None:
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)

    def render_title(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        text = self.item.title
        layout = widget.create_pango_layout(text)
        layout.set_markup(self.markup['title'].format(text=html.escape(text),
                          color=utils.hexcolor(color), weight='bold'))
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_ellipsize(Pango.EllipsizeMode.END)

        ink = layout.get_pixel_extents()[0]
        if ctx is not None and cell_area is not None:
            layout.set_width(cell_area.width * Pango.SCALE)
            ctx.move_to(cell_area.x, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_summary(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        text = self.item.summary
        layout = widget.create_pango_layout(text)
        layout.set_markup(self.markup['summary'].format(text=html.escape(text),
                          color=utils.hexcolor(color)))
        layout.set_ellipsize(Pango.EllipsizeMode.END)

        ink = layout.get_pixel_extents()[0]
        if ctx is not None and cell_area is not None:
            layout.set_width(cell_area.width * Pango.SCALE)
            ctx.move_to(cell_area.x, y)
            PangoCairo.show_layout(ctx, layout)
        return ink
