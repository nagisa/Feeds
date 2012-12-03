from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Pango
from gi.repository import PangoCairo

from trifle import models
from trifle.views import utils


class ItemCellRenderer(Gtk.CellRenderer):
    title = GObject.property(type=GObject.TYPE_STRING)
    summary = GObject.property(type=GObject.TYPE_STRING)
    time = GObject.property(type=GObject.TYPE_UINT64)
    unread = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    source = GObject.property(type=GObject.TYPE_STRING)
    source_title = GObject.property(type=GObject.TYPE_STRING)
    # Some style properties
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
        state = self.get_state(view, flags)
        text_color = view.get_style_context().get_color(state)

        ctx.save()
        ctx.move_to(area.x, area.y)
        # Render icon
        ctx.save()
        x, y = ctx.get_current_point()
        self.render_icon(ctx, self.source, self.icon_size, x, y)
        ctx.restore()
        # Center vertically
        tmp_layout = view.create_pango_layout('Gg')
        dh = int(self.icon_size - tmp_layout.get_pixel_extents()[1].height)
        ctx.rel_move_to(self.icon_size + self.line_spacing, dh)
        # Render time
        time = utils.time_ago(self.time)
        kwargs = {'width': area.width - self.icon_size - self.line_spacing,
                  'align': Pango.Alignment.RIGHT, 'color': text_color}
        h, w = self.render_text(view, ctx, time, **kwargs)
        # Render subscription title
        kwargs = {'width': area.width - self.icon_size - w - self.line_spacing,
                  'color': text_color}
        self.render_text(view, ctx, self.source_title, **kwargs)

        # Render title
        ctx.move_to(area.x, area.y + self.icon_size + self.line_spacing)
        kwargs = {'size': self.title_size, 'width': area.width,
                  'bold': self.unread, 'color': text_color}
        h, w = self.render_text(view, ctx, self.title, **kwargs)
        # Render summary
        ctx.rel_move_to(0, h + self.line_spacing)
        kwargs = {'width': area.width, 'color': text_color}
        self.render_text(view, ctx, self.summary, **kwargs)
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
                    bold=False, align=None, color=None):

        layout = view.create_pango_layout(text)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        if width is not None:
            layout.set_width(width * Pango.SCALE)
        if height is not None:
            layout.set_height(height * Pango.SCALE)
        if align is not None:
            layout.set_alignment(align)

        # I'm feelin so ninja doing things introspection doesn't let me do with
        # introspection.
        # Coincidentally I really don't want to go and fix Pango introspection
        # after this 😨
        if color is not None:
            attrlist = []
            def filter_cb(attr, attrlist):
                attrlist.append(attr)
                return False
            color_hex = color.to_color().to_string()
            markup = '<span color="{0}"></span>'.format(color_hex)
            attrs = Pango.parse_markup(markup, -1, '\01')[1]
            attrs.filter(filter_cb, attrlist)
            attrlist[0].end_index = GLib.MAXINT32
            layout.set_attributes(attrs)

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
