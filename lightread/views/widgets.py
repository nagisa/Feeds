# -*- coding: utf-8 -*-
from gi.repository import Gtk, WebKit, Pango, PangoCairo, GdkPixbuf, Gdk, GObject
import html
import os
import collections
import datetime

from lightread.views import utils
from lightread import models
from lightread.utils import get_data_path

class ToolbarSearch(Gtk.ToolItem):

    def __init__(self, *args, **kwargs):
        super(ToolbarSearch, self).__init__(*args, **kwargs)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(_('Search {0} items').format(0))
        self.entry.set_size_request(200, 0)
        self.add(self.entry)


class Toolbar(Gtk.Toolbar):

    def __init__(self, *args, **kwargs):
        super(Toolbar, self).__init__(*args, **kwargs)
        Gtk.StyleContext.add_class(self.get_style_context(),
                                   Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        # Reload button
        self.reload = Gtk.ToolButton.new_from_stock(Gtk.STOCK_REFRESH)
        self.insert(self.reload, -1)
        # Add button
        self.add_button = Gtk.ToolButton.new_from_stock(Gtk.STOCK_ADD)
        self.insert(self.add_button, -1)
        # Separator
        sep = Gtk.SeparatorToolItem()
        self.insert(sep, -1)
        # All read button
        self.read_button = Gtk.ToolButton.new_from_stock(Gtk.STOCK_APPLY)
        self.insert(self.read_button, -1)
        # Search bar
        self.search = ToolbarSearch()
        self.insert(self.search, -1)
        # Separator
        sep = Gtk.SeparatorToolItem()
        self.insert(sep, -1)
        # Star
        self.star = Gtk.ToolButton.new_from_stock(Gtk.STOCK_YES)
        self.insert(self.star, -1)
        # Share
        self.share = Gtk.ToolButton.new_from_stock(Gtk.STOCK_REDO)
        self.insert(self.share, -1)
        # Preferences
        self.preferences = Gtk.ToolButton.new_from_stock(Gtk.STOCK_PREFERENCES)
        self.preferences.set_halign(Gtk.Align.END)
        self.preferences.set_expand(True)
        self.insert(self.preferences, -1)

class Sidebar(Gtk.HPaned):
    __gsignals__ = {
        'change-items': (GObject.SignalFlags.ACTION, None, []),
    }

    def __init__(self, *args, **kwargs):
        super(Sidebar, self).__init__(*args, **kwargs)
        # Left side.
        left_box = Gtk.VBox()
        left_box.set_size_request(150, 0)
        Gtk.StyleContext.add_class(left_box.get_style_context(),
                                   Gtk.STYLE_CLASS_SIDEBAR)

        # Upper part
        self.categories = CategoriesView()
        # TODO: Change with custom icons.
        left_box.pack_start(self.categories, False, False, 0)

        # Bottom part
        self.subscriptions = SubscriptionsView()
        left_box.pack_start(self.subscriptions.scrollwindow, True, True, 0)
        self.pack1(left_box, False, False)

        # Make middle sidebar

        self.items = ItemsView()
        self.items.scrollwindow.set_size_request(250, 0)
        self.pack2(self.items.scrollwindow, True, False)

        # Connecting signals

        self.subscriptions.connect('cursor-changed', self.on_change)
        self.categories.connect('cursor-changed', self.on_change)
        # Need to register manually, because self.categories selects
        # first row in __init__
        self.on_change(self.categories)

    def on_reload(self, button):
        self.subscriptions.sync()
        self.items.sync()

    def on_change(self, view):
        if view.in_destruction():
            return
        if isinstance(view, CategoriesView):
            self.subscriptions.selection.unselect_all()
            selection = self.categories.selection.get_selected()
            category = selection[0].get_value(selection[1], 2)
            self.items.reloading = True
            self.items.store.set_category(category)
            self.items.reloading = False
        else:
            pass


class FeedView(WebKit.WebView, utils.ScrollWindowMixin):

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

        self.set_headers_visible(False)
        self.set_enable_search(False)
        self.set_margin_bottom(5)

        column = Gtk.TreeViewColumn("Icon and Title")
        icon = Gtk.CellRendererPixbuf()
        title = Gtk.CellRendererText(scale=1.2)
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


class SubscriptionsView(Gtk.TreeView, utils.ScrollWindowMixin):

    def __init__(self, *args, **kwargs):
        self.store = models.Subscriptions()
        super(SubscriptionsView, self).__init__(self.store, *args,
                                                **kwargs)
        self.store.connect('pre-clear', self.on_pre_clear)
        self.store.connect('sync-done', self.on_sync_done)
        self.connect('row-collapsed', SubscriptionsView.on_collapse)
        self.connect('row-expanded', SubscriptionsView.on_expand)
        self.memory = {'expanded': [], 'selection': None}
        self.set_headers_visible(False)
        self.set_level_indentation(-12)
        self.selection = self.get_selection()
        Gtk.StyleContext.add_class(self.get_style_context(),
                                   Gtk.STYLE_CLASS_SIDEBAR)

        # Make column
        column = Gtk.TreeViewColumn("Subscription")
        icon_renderer = Gtk.CellRendererPixbuf()
        title_renderer = Gtk.CellRendererText()
        column.pack_start(icon_renderer, False)
        column.pack_start(title_renderer, True)
        column.add_attribute(icon_renderer, "pixbuf", 0)
        column.add_attribute(title_renderer, "text", 1)
        title_renderer.set_properties(ellipsize=Pango.EllipsizeMode.END,
                                      ellipsize_set=True)
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

    def sync(self):
        logger.debug('Starting subscriptions\' sync')
        self.store.sync()


class ItemsView(Gtk.TreeView, utils.ScrollWindowMixin):
    def __init__(self, *args, **kwargs):
        self.reloading = False
        self.store = models.Items()
        super(ItemsView, self).__init__(self.store, *args, **kwargs)
        self.set_headers_visible(False)
        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer, item=0)
        self.append_column(column)
        self.store.set_sort_column_id(0, Gtk.SortType.DESCENDING)
        self.store.set_sort_func(0, models.Items.compare, None)

    def sync(self):
        logger.debug('Starting items\' sync')
        self.store.sync()

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
