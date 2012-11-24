from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import PangoCairo

from trifle.models.base import Item
from trifle.models.utils import escape
from trifle.views import utils


class ItemCellRenderer(Gtk.CellRenderer):
    item = GObject.property(type=Item)

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
        #icon_w, icon_h = self.render_icon(y, x, context)
        icon_w, icon_h = 0, self.icon_size
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
