from gi.repository import Gtk, WebKit, Gdk, Pango, PangoCairo
from lightread.views import utils
from lightread import models


class ToolbarSearch(Gtk.ToolItem):

    def __init__(self, *args, **kwargs):
        super(ToolbarSearch, self).__init__(*args, **kwargs)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text('Search 123 items')
        self.entry.set_size_request(200, 0)
        self.add(self.entry)


class Toolbar(Gtk.Toolbar):

    def __init__(self, *args, **kwargs):
        super(Toolbar, self).__init__(*args, **kwargs)
        Gtk.StyleContext.add_class(self.get_style_context(),
                                   Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        # Reload button
        self.reload_button = Gtk.ToolButton.new_from_stock(Gtk.STOCK_REFRESH)
        self.insert(self.reload_button, -1)
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
        for entry in [(Gtk.STOCK_JUSTIFY_FILL, 'All items',),
                      (Gtk.STOCK_INDEX, 'Unread',),
                      (Gtk.STOCK_ABOUT, 'Starred',)]:
            self.categories.add_category(*entry)

        left_box.pack_start(self.categories, False, False, 0)

        # Bottom part
        self.subscriptions = SubscriptionsView()

        # Dummy data
        for i in range(10):
            directory = self.subscriptions.add_directory('Directory')
            for i in range(10):
                self.subscriptions.add_feed(Gtk.STOCK_FILE, 'Feed', directory)

        for i in range(10):
            self.subscriptions.add_feed(Gtk.STOCK_FILE, 'Feed')

        left_box.pack_start(self.subscriptions.scrollwindow, True, True, 0)


        self.pack1(left_box, False, False)

        # Make middle sidebar

        self.items = ItemsView()
        self.items.scrollwindow.set_size_request(250, 0)
        self.pack2(self.items.scrollwindow, True, False)


class FeedView(WebKit.WebView, utils.ScrollWindowMixin):

    def __init__(self, *args, **kwargs):
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

    def __init__(self, *args, **kwargs):
        self._store = Gtk.ListStore(str, str)
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

    def add_category(self, icon, title):
        return self._store.append((icon, title,))


class SubscriptionsView(Gtk.TreeView, utils.ScrollWindowMixin):

    def __init__(self, *args, **kwargs):
        self._store = Gtk.TreeStore(str, str)

        super(SubscriptionsView, self).__init__(self._store, *args,
                                                **kwargs)
        self.set_headers_visible(False)
        # Somewhy removes color from selected rows as well.
        # self.override_background_color(Gtk.StateFlags.NORMAL,
        #                                Gdk.RGBA(0, 0, 0, 0))
        Gtk.StyleContext.add_class(self.get_style_context(),
                                   Gtk.STYLE_CLASS_SIDEBAR)

        # Make column
        _column = Gtk.TreeViewColumn("Icon and Title")
        _icon_renderer = Gtk.CellRendererPixbuf()
        _title_renderer = Gtk.CellRendererText()
        _column.pack_start(_icon_renderer, False)
        _column.pack_start(_title_renderer, True)
        _column.add_attribute(_icon_renderer, "icon-name", 0)
        _column.add_attribute(_title_renderer, "text", 1)
        self.append_column(_column)

    def add_directory(self, title):
        """ Returns appended directory, which you need to use to append feeds.
        """
        return self._store.append(None, (None, title,))

    def add_feed(self, icon, title, directory=None):
        self._store.append(directory, (icon, title,))


class ItemsView(Gtk.TreeView, utils.ScrollWindowMixin):
    def __init__(self, *args, **kwargs):
        self._store = Gtk.ListStore(models.Feed) # Temp
        super(ItemsView, self).__init__(self._store, *args, **kwargs)

        self._store.append((models.Feed(),))

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer)
        self.append_column(column)


class ItemCellRenderer(Gtk.CellRenderer):
    # Borrowed from Geary.

    def __init__(self, *args, **kwargs):
        print(*args, **kwargs)
        super(ItemCellRenderer, self).__init__(*args, **kwargs)
        self.site_size = 9
        self.title_size = 11
        self.summary_size = 8
        self.summary_height = 0
        self.line_spacing = 7
        self.left_padding = 16
        self.height = 0

    def do_render(self, ctx, widget, bg_area, cell_area, flags):
        self._do_render(widget, ctx, cell_area, flags.SELECTED)

    def _do_render(self, widget, ctx=None, cell_area=None, selected=False):
        # TODO: the magic.
        # HINT: it's gonna be hardest part.
        celly = (0 if cell_area is None else cell_area.y)
        y = self.line_spacing + celly
        ink = self.render_date(widget, cell_area, ctx, y)
        self.render_site(widget, cell_area, ctx, y, ink)
        y += ink.height + ink.y + self.line_spacing
        ink = self.render_title(widget, cell_area, ctx, y)
        y += ink.height + self.line_spacing
        # Calculate height here smartly
        ink = self.render_summary(widget, cell_area, ctx, y)
        y += ink.height + self.line_spacing + celly
        self.height = y

    def do_get_size(self, widget, cell_area):
        if self.height == 0:
            self._do_render(widget)
        return 0, 0, 0, self.height

    def render_date(self, widget, cell_area, ctx, y):
        text = '2012-03-11 12:34'
        font_desc = Pango.FontDescription()
        font_desc.set_size(self.site_size * Pango.SCALE)
        mark = '<span color="{0}">{1}</span>'.format('#2727d6', text)
        font_attrs = Pango.parse_markup(mark, -1, "§")[1]
        layout = widget.create_pango_layout(text)
        layout.set_attributes(font_attrs)
        layout.set_font_description(font_desc)
        layout.set_alignment(Pango.Alignment.RIGHT)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            x = cell_area.width - cell_area.x - ink.width - self.line_spacing - ink.x
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_site(self, widget, cell_area, ctx, y, ink):
        text = "The Blog and a the humble long long title"
        font_desc = Pango.FontDescription()
        font_desc.set_size(self.site_size * Pango.SCALE)
        layout = widget.create_pango_layout(text)
        layout.set_font_description(font_desc)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - ink.width - ink.x -
                        self.line_spacing - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_title(self, widget, cell_area, ctx, y):
        text = "How I did that, then that, and then this and that"
        font_desc = Pango.FontDescription()
        font_desc.set_size(self.title_size * Pango.SCALE)
        mark = '<b>{0}</b>'.format(text)
        font_attrs = Pango.parse_markup(mark, -1, "§")[1]
        layout = widget.create_pango_layout(text)
        layout.set_attributes(font_attrs)
        layout.set_font_description(font_desc)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE);
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink

    def render_summary(self, widget, cell_area, ctx, y):
        text = "Last day I did that, then I did this, but after that another thing was done. At last I did that but then I did nothing"

        font_desc = Pango.FontDescription()
        font_desc.set_size(self.summary_size * Pango.SCALE)
        layout = widget.create_pango_layout(text)
        layout.set_font_description(font_desc)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_height(self.summary_height * Pango.SCALE)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink
