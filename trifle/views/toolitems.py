from gi.repository import GObject
from gi.repository import Gtk

from trifle.utils import logger


class ToolLinkedButtons(Gtk.ToolItem):
    buttons = GObject.property(type=object)
    current_id = GObject.property(type=GObject.TYPE_STRING)

    def __init__(self, *args, **kwargs):
        super(ToolLinkedButtons, self).__init__(*args, **kwargs)
        self.buttons = {}

        self.button_box = Gtk.Box()
        self.button_box.get_style_context().add_class('linked')
        self.add(self.button_box)
        self.connect('toolbar-reconfigured', self.on_reconfigure)

    def add_button(self, button_id, button_widget):
        if button_id in self.buttons:
            logger.warning('Adding a button with ID of another button')

        self.button_box.pack_start(button_widget, False, True, 0)
        button_widget.connect('toggled', self.on_toggle, button_id)
        if len(self.buttons) > 0:
            key = next(iter(self.buttons.keys()))
            button_widget.set_property('group', self.buttons[key])

        self.buttons[button_id] = button_widget
        self.notify('buttons')

    def on_toggle(self, button, key):
        if not button.get_active():
            return
        self.current_id = key

    @staticmethod
    def on_reconfigure(self):
        relief = self.get_relief_style()
        for button in self.buttons.values():
            button.set_relief(relief)


class ToolLabel(Gtk.ToolItem):
    def __init__(self, *args, **kwargs):
        super(ToolLabel, self).__init__(*args, **kwargs)
        self.label = Gtk.Label()
        self.add(self.label)


class ToolLinkButton(Gtk.ToolItem):
    uri = GObject.property(type=GObject.TYPE_STRING)
    label = GObject.property(type=GObject.TYPE_STRING)

    def __init__(self, *args, **kwargs):
        super(ToolLinkButton, self).__init__(*args, **kwargs)
        button = Gtk.LinkButton('127.0.0.1')
        self.bind_property('uri', button, 'uri',
                           GObject.BindingFlags.BIDIRECTIONAL)
        self.bind_property('label', button, 'label',
                           GObject.BindingFlags.BIDIRECTIONAL)
        self.add(button)
        button.show()
        self.connect('toolbar-reconfigured', self.on_reconfigure)

    @staticmethod
    def on_reconfigure(self, data=None):
        self.get_child().set_relief(self.get_relief_style())
