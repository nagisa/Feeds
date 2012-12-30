import sqlite3
from gi.repository import Soup
from gi.repository import Gtk

from trifle.utils.common import get_data_path
from trifle.utils.const import VERSION

class Message(Soup.Message):
    def __new__(cls, *args, **kwargs):
        obj = Soup.Message.new(*args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('User-Agent', 'Trifle/{0}'.format(VERSION))
        return obj


class AuthMessage(Message):
    """
    Creates an Soup.Message object with GoogleLogin headers injected
    """
    def __new__(cls, auth, *args, **kwargs):
        obj = super(AuthMessage, cls).__new__(cls, *args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('Authorization',
                   'GoogleLogin auth={0}'.format(auth.login_token))
        return obj


class TreeModelFilter(Gtk.TreeModelFilter):
    def set_value(self, iter, column, val):
        # Delegate change to parent
        iter = self.convert_iter_to_child_iter(iter)
        self.get_model().set_value(iter, column, val)


class BuiltMixin:
    def __new__(cls, *args, **kwargs):
        # Avoid getting __init__ called during building.
        try:
            cls_init = cls.__init__
            delattr(cls, '__init__')
        except AttributeError:
            cls_init = None

        builder = Gtk.Builder(translation_domain='trifle')
        path = get_data_path('ui', cls.ui_file)
        builder.add_from_file(path)
        parent = builder.get_object(cls.top_object)
        builder.connect_signals(parent)
        parent._builder = builder

        # But let it be executed when initializing object normally
        if cls_init is not None:
            cls.__init__ = cls_init
        return parent
