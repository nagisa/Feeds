from gi.repository import GObject, Gtk

class Item(GObject.Object):
    # https://bugzilla.gnome.org/show_bug.cgi?id=688949
    item_id = GObject.property(type=object)
    title = GObject.property(type=GObject.TYPE_STRING)
    author = GObject.property(type=GObject.TYPE_STRING)
    summary = GObject.property(type=GObject.TYPE_STRING)
    href = GObject.property(type=GObject.TYPE_STRING)
    time = GObject.property(type=GObject.TYPE_UINT64)
    unread = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    starred = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    origin = GObject.property(type=GObject.TYPE_STRING)
    site = GObject.property(type=GObject.TYPE_STRING)
    icon = GObject.property(type=GObject.TYPE_STRING)


class ItemsStore(Gtk.ListStore):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_FIRST, None, []),
        'load-done': (GObject.SignalFlags.RUN_LAST, None, [])
    }
    category = GObject.property(type=GObject.TYPE_STRING)
    subscription = GObject.property(type=GObject.TYPE_STRING)
    is_feed = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    flags = GObject.property(type=GObject.Object)

    def __init__(self, *args, **kwargs):
        super(ItemsStore, self).__init__(Item, *args, **kwargs)


class SyncObject(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    sync_status = GObject.property(type=object)
