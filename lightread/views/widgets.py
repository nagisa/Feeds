# -*- coding: utf-8 -*-
from gi.repository import Gtk, WebKit, Pango, PangoCairo, GdkPixbuf, Gdk
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
        for entry in [(Gtk.STOCK_JUSTIFY_FILL, _('All items'),),
                      (Gtk.STOCK_INDEX, _('Unread'),),
                      (Gtk.STOCK_ABOUT, _('Starred'),)]:
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
    # TODO: Box of trees
    def __init__(self, *args, **kwargs):
        self._store = Gtk.ListStore(models.Feed) # Temp
        super(ItemsView, self).__init__(self._store, *args, **kwargs)

        self._store.append((models.Feed(),))

        renderer = ItemCellRenderer()
        column = Gtk.TreeViewColumn("Item", renderer)
        self.append_column(column)


class ItemCellRenderer(Gtk.CellRenderer):
    # Borrowed from Geary.
    markup = {'date': '<span color="{color}" size="{size}">{text}</span>',
              'site': '<span color="{color}" size="{size}">{text}</span>',
              'title': '<span color="{color}" size="{size}" weight="bold">{text}</span>',
              'summary': '<span color="{color}" size="{size}">{text}</span>'}
    font_size = {'date': 9, 'site': 9, 'title': 10, 'summary': 8}



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
        return Pango.parse_markup(mark, -1, "§")[1]

    def render_icon(self, widget, cell_area, ctx, y):
        return
        if ctx is not None and cell_area is not None:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size('', 16, 16)
            Gdk.cairo_set_source_pixbuf(ctx, pixbuf, cell_area.x, y)
            ctx.paint()
            self.left_padding = pixbuf.get_width() + cell_area.x
            print(self.left_padding)


    def render_date(self, widget, cell_area, ctx, y):
        # TODO: Use locale specific date formatting
        text = '12:34'
        context = widget.get_style_context()
        if not self.selected:
            color = context.get_background_color(Gtk.StateFlags.SELECTED)
        else:
            color = context.get_color(Gtk.StateFlags.SELECTED)
        attrs = self.get_attrs('date', text=text, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(text)
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
        text = "The Blog and a the humble long long title"
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('site', text=text, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(text)
        layout.set_attributes(attrs)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if ctx is not None and cell_area is not None:
            width = (date_x - self.left_padding - self.line_spacing)
            layout.set_width(width * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)

    def render_title(self, widget, cell_area, ctx, y):
        text = "How I did that, then that, and then this and that"
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('title', text=text, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(text)
        layout.set_attributes(attrs)
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
        color = widget.get_style_context().get_color(self.state)
        attrs = self.get_attrs('summary', text=text, color=utils.hexcolor(color))
        layout = widget.create_pango_layout(text)
        layout.set_attributes(attrs)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_height(self.summary_height * Pango.SCALE)
        ink, logical = layout.get_pixel_extents()
        if ctx is not None and cell_area is not None:
            layout.set_width((cell_area.width - self.left_padding) * Pango.SCALE)
            ctx.move_to(cell_area.x + self.left_padding, y)
            PangoCairo.show_layout(ctx, layout)
        return ink
