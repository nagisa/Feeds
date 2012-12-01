from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import PangoCairo

from trifle import models
from trifle.views import utils


class ItemCellRenderer(Gtk.CellRenderer):
    item = GObject.property(type=models.base.Item)
    icon_size = GObject.property(type=GObject.TYPE_UINT, default=16)
    title_size = GObject.property(type=GObject.TYPE_DOUBLE, default=1.15)
    line_spacing = GObject.property(type=GObject.TYPE_INT, default=2)
    height = GObject.property(type=GObject.TYPE_UINT, default=0)

    def __init__(self, *args, **kwargs):
        super(ItemCellRenderer, self).__init__(*args, **kwargs)

    def do_get_preferred_height(self, view):
        if self.height == 0:
            layout = view.create_pango_layout('Gg')
            self.height = self.line_spacing * 2
            self.height += self.icon_size
            self.height += layout.get_pixel_extents()[1].height
            descr = layout.get_context().get_font_description().copy()
            descr.set_size(descr.get_size() * self.title_size)
            layout.set_font_description(descr)
            self.height += layout.get_pixel_extents()[1].height
        return self.height, self.height

    # Any of render functions should not modify self.* in any way
    def do_render(self, ctx, view, bg_area, area, flags):
        if self.item is None and not self.item.is_presentable():
            return

        ctx.save()
        ctx.move_to(area.x, area.y)
        # Render icon
        ctx.save()
        x, y = ctx.get_current_point()
        self.render_icon(ctx, self.item.origin, self.icon_size, x, y)
        ctx.restore()
        # Center vertically
        tmp_layout = view.create_pango_layout('Gg')
        dh = int(self.icon_size - tmp_layout.get_pixel_extents()[1].height)
        ctx.rel_move_to(self.icon_size + self.line_spacing, dh)
        # Render time
        time = utils.time_ago(self.item.time)
        kwargs = {'width': area.width - self.icon_size - self.line_spacing,
                  'align': Pango.Alignment.RIGHT}
        h, w = self.render_text(view, ctx, time, **kwargs)
        # Render subscription title
        kwargs = {'width': area.width - self.icon_size - w - self.line_spacing}
        self.render_text(view, ctx, self.item.site, **kwargs)

        # Render title
        ctx.move_to(area.x, area.y + self.icon_size + self.line_spacing)
        kwargs = {'size': self.title_size, 'width': area.width,
                  'bold': self.item.unread}
        h, w = self.render_text(view, ctx, self.item.title, **kwargs)
        # Render summary
        ctx.rel_move_to(0, h + self.line_spacing)
        self.render_text(view, ctx, self.item.summary, width=area.width)
        ctx.restore()

    @staticmethod
    def render_icon(context, uri, size, x, y):
        pixbuf = models.utils.icon_pixbuf(uri)
        if pixbuf is None:
            return
        Gdk.cairo_set_source_pixbuf(context, pixbuf, x, y)
        context.paint()

    @staticmethod
    def render_text(view, context, text, size=1, width=None, height=None,
                    bold=False, align=None):
        layout = view.create_pango_layout(text)
        layout.set_text(text, len(text))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if width is not None:
            layout.set_width(width * Pango.SCALE)
        if height is not None:
            layout.set_height(height * Pango.SCALE)
        if align is not None:
            layout.set_alignment(align)

        if size != 1 or bold:
            descr = layout.get_context().get_font_description().copy()
            if size != 1:
                descr.set_size(descr.get_size() * size)
            if bold:
                descr.set_weight(Pango.Weight.BOLD)
            layout.set_font_description(descr)
        PangoCairo.show_layout(context, layout)

        rect = layout.get_pixel_extents()[1]
        return rect.height, rect.width
