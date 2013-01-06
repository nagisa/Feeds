from gi.repository import GObject
from gi.repository import Gtk


class ToolLinkedButtonBox(Gtk.ToolItem):
    current_name = GObject.property(type=GObject.TYPE_STRING)

    def __init__(self, *args, **kwargs):
        super(ToolLinkedButtonBox, self).__init__(*args, **kwargs)

        self.button_box = Gtk.Box()
        self.button_box.get_style_context().add_class('linked')
        Gtk.ToolItem.do_add(self, self.button_box)
        self.connect('toolbar-reconfigured', self.on_reconfigure)

    def do_add(self, widget):
        name = widget.get_property('name')
        widget.connect('toggled', self.on_toggle, name)
        self.button_box.pack_start(widget, False, True, 0)

    def on_toggle(self, button, name):
        if button.get_active():
            self.current_name = name

    def on_reconfigure(self, *args):
        relief = self.get_relief_style()
        for button in self.button_box.get_children():
            button.set_relief(relief)


class ToolLinkButton(Gtk.ToolItem):
    def __init__(self, *args, **kwargs):
        super(ToolLinkButton, self).__init__(*args, **kwargs)
        button = Gtk.LinkButton('')
        self.add(button)
        self.connect('toolbar-reconfigured', self.on_reconfigure)

    def do_show(self):
        Gtk.ToolItem.do_show(self)
        self.get_child().show_all()

    def on_reconfigure(self, *args):
        self.get_child().set_relief(self.get_relief_style())


GObject.type_register(ToolLinkButton)
GObject.type_register(ToolLinkedButtonBox)
