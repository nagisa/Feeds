# -*- coding: utf-8 -*-
from gi.repository import Gtk, WebKit, Pango, PangoCairo, GdkPixbuf, Gdk, GObject
from lightread.views import utils
from lightread import models


class ToolbarSearch(Gtk.ToolItem):

    def __init__(self, *args, **kwargs):
        super(ToolbarSearch, self).__init__(*args, **kwargs)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(_('Search {0} items').format(0))
        self.entry.set_size_request(200, 0)
        self.add(self.entry)


class Toolbar(Gtk.Toolbar):

    def __init__(self, application, *args, **kwargs):
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

    def __init__(self, application, *args, **kwargs):
        super(Sidebar, self).__init__(*args, **kwargs)
        # Left side.
        left_box = Gtk.VBox()
        left_box.set_size_request(150, 0)
        Gtk.StyleContext.add_class(left_box.get_style_context(),
                                   Gtk.STYLE_CLASS_SIDEBAR)

        # Upper part
        self.categories = CategoriesView(application)
        # TODO: Change with custom icons.
        left_box.pack_start(self.categories, False, False, 0)

        # Bottom part
        self.subscriptions = SubscriptionsView(application)
        left_box.pack_start(self.subscriptions.scrollwindow, True, True, 0)
        self.pack1(left_box, False, False)

        # Make middle sidebar

        self.items = ItemsView(application)
        self.items.scrollwindow.set_size_request(250, 0)
        self.pack2(self.items.scrollwindow, True, False)
        application.toolbar.reload.connect('clicked', self.on_reload)

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
            self.items.store.set_category(category)
        else:
            pass


class FeedView(WebKit.WebView, utils.ScrollWindowMixin):

    def __init__(self, application, *args, **kwargs):
        super(FeedView, self).__init__(*args, **kwargs)
        self.settings = WebKit.WebSettings()
        self.settings.set_properties(
            # These three saves us ~25MiB of residental memory
            enable_scripts=False, enable_plugins=False,
            enable_java_applet=False,
            # We already have most files cached and load locally
            enable_page_cache=False, enable_dns_prefetching=False,
            enable_universal_access_from_file_uris=True,
            # Need this one of usability reasons.
            enable_default_context_menu=False,
            # Not used
            enable_html5_database=False, enable_html5_local_storage=False,
            enable_offline_web_application_cache=False,
            enable_xss_auditor=False, resizable_text_areas=False,
            # Very effectively turns off all types of cache
            enable_private_browsing=True
        )
        self.set_settings(self.settings)


class CategoriesView(Gtk.TreeView):

    def __init__(self, application, *args, **kwargs):
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

    def __init__(self, application, *args, **kwargs):
        self.store = models.Subscriptions()
        super(SubscriptionsView, self).__init__(self.store, *args,
                                                **kwargs)
        self.store.connect('pre-clear', self.on_pre_clear)
        self.store.connect('sync-done', self.on_sync_done)
        self.connect('row-collapsed', SubscriptionsView.on_collapse)
        self.connect('row-expanded', SubscriptionsView.on_expand)
        self.memory = {'expanded': [], 'selection': None}
        self.set_headers_visible(False)
        self.set_level_indentation(-16)
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
    def __init__(self, application, *args, **kwargs):
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
    # Borrowed from Geary.
    item = GObject.property(type=models.FeedItem)
    markup = {'date': '<span color="{color}" size="{size}">{text}</span>',
              'site': '<span color="{color}" size="{size}">{text}</span>',
              'title': '<span color="{color}" size="{size}" weight="bold">{text}</span>',
              'summary': '<span color="{color}" size="{size}">{text}</span>'}
    font_size = {'date': 9, 'site': 9, 'title': 10, 'summary': 9}

    def __init__(self, *args, **kwargs):
        super(ItemCellRenderer, self).__init__(*args, **kwargs)
        self.summary_height = 0
        self.line_spacing = 6
        self.left_padding = 0 # Replaced later by render_icon
        self.height = 0

    def do_render(self, ctx, widget, bg_area, cell_area, flags):
        self._do_render(widget, ctx, cell_area, flags & flags.SELECTED)

    def _do_render(self, widget, ctx=None, cell_area=None, selected=False):
        # TODO: Employ current GTK theme colors.
        # It should be possible, but I'll do it later
        self.selected = selected
        self.state = (Gtk.StateFlags.SELECTED if self.selected else
                                                        Gtk.StateFlags.NORMAL)
        y = self.line_spacing
        if cell_area is not None:
            y += cell_area.y
        self.render_icon(widget, cell_area, ctx, y)
        ink, date_x = self.render_date(widget, cell_area, ctx, y)
        self.render_site(widget, cell_area, ctx, y, date_x)
        y += ink.height + self.line_spacing
        ink = self.render_title(widget, cell_area, ctx, y)
        y += ink.height + self.line_spacing
        ink = self.render_summary(widget, cell_area, ctx, y)
        y += ink.height + self.line_spacing
        self.height = y

    def do_get_size(self, widget, cell_area):
        if self.height == 0:
            self._do_render(widget)
        return 0, 0, 0, self.height

    def get_attrs(self, t, **kwargs):
        mark = self.markup[t].format(size=self.font_size[t] * Pango.SCALE,
                                     **kwargs)
        try:
            return Pango.parse_markup(mark, -1, "§")[1]
        except:
            logger.error('Could not get attributes, because of malformed'
                         ' markup')
            return Pango.parse_markup('', -1, "§")[1]


    def render_icon(self, widget, cell_area, ctx, y):
        if ctx is not None and cell_area is not None and \
           self.item.icon is not None:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.item.icon, 16, 16)
            Gdk.cairo_set_source_pixbuf(ctx, pixbuf, cell_area.x, y)
            ctx.paint()
            self.left_padding = pixbuf.get_width() + cell_area.x
        elif cell_area is not None:
            self.left_padding = cell_area.x


    def render_date(self, widget, cell_area, ctx, y):
        time = utils.time_ago(self.item.datetime)
        context = widget.get_style_context()
        if not self.selected:
            color = context.get_background_color(Gtk.StateFlags.SELECTED)
        else:
            color = context.get_color(Gtk.StateFlags.SELECTED)
        attrs = self.get_attrs('date', text=time, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(time)
        layout.set_attributes(attrs)
        layout.set_alignment(Pango.Alignment.RIGHT)
        ink, logical = layout.get_pixel_extents()
        x = None
        if ctx is not None and cell_area is not None:
            x = cell_area.width - cell_area.x - ink.width - ink.x
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, layout)
        return ink, x

    def render_site(self, widget, cell_area, ctx, y, date_x):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('site', text=self.item.site,
                               color=utils.hexcolor(color))
        layout = widget.create_pango_layout(self.item.site)
        layout.set_attributes(attrs)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if ctx is not None and cell_area is not None:
            width = (date_x - self.left_padding - self.line_spacing)
            layout.set_width(width * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)

    def render_title(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('title', text=self.item.title,
                                                  color=utils.hexcolor(color))
        layout = widget.create_pango_layout(self.item.title)
        layout.set_attributes(attrs)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_summary(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('summary', text=self.item.summary,
                               color=utils.hexcolor(color))

    def render_icon(self, widget, cell_area, ctx, y):
        if ctx is not None and cell_area is not None and \
           self.item.icon is not None:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.item.icon, 16, 16)
            Gdk.cairo_set_source_pixbuf(ctx, pixbuf, cell_area.x, y)
            ctx.paint()
            self.left_padding = pixbuf.get_width() + cell_area.x
        elif cell_area is not None:
            self.left_padding = cell_area.x


    def render_date(self, widget, cell_area, ctx, y):
        time = utils.time_ago(self.item.datetime)
        context = widget.get_style_context()
        if not self.selected:
            color = context.get_background_color(Gtk.StateFlags.SELECTED)
        else:
            color = context.get_color(Gtk.StateFlags.SELECTED)
        attrs = self.get_attrs('date', text=time, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(time)
        layout.set_attributes(attrs)
        layout.set_alignment(Pango.Alignment.RIGHT)
        ink, logical = layout.get_pixel_extents()
        x = None
        if ctx is not None and cell_area is not None:
            x = cell_area.width - cell_area.x - ink.width - ink.x
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, layout)
        return ink, x

    def render_site(self, widget, cell_area, ctx, y, date_x):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('site', text=self.item.site,
                               color=utils.hexcolor(color))
        layout = widget.create_pango_layout(self.item.site)
        layout.set_attributes(attrs)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if ctx is not None and cell_area is not None:
            width = (date_x - self.left_padding - self.line_spacing)
            layout.set_width(width * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)

    def render_title(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('title', text=self.item.title,
                                                  color=utils.hexcolor(color))
        layout = widget.create_pango_layout(self.item.title)
        layout.set_attributes(attrs)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_summary(self, widget, cell_area, ctx, y):
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('summary', text=self.item.summary,
                               color=utils.hexcolor(color))
        layout = widget.create_pango_layout(self.item.summary)
        layout.set_attributes(attrs)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_height(self.summary_height * Pango.SCALE)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink
