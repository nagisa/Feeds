from gi.repository import GObject, Gtk


class ItemsStore(Gtk.ListStore):
    __gsignals__ = {
        'load-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    is_feed = GObject.property(type=GObject.TYPE_BOOLEAN, default=False)
    flags = GObject.property(type=GObject.Object)

    def __init__(self, *args, **kwargs):
        base_cols = (object, # Item ID
                     GObject.TYPE_STRING, # Title
                     GObject.TYPE_STRING, # Summary
                     GObject.TYPE_STRING, # Link to document
                     GObject.TYPE_UINT64, # Timestamp
                     GObject.TYPE_BOOLEAN, # Is item unread
                     GObject.TYPE_BOOLEAN, # Is item starred
                     GObject.TYPE_STRING, # Subscription URI
                     GObject.TYPE_STRING, # Subscription Title
                     GObject.TYPE_STRING, # Subscription ID
                     GObject.TYPE_STRING,) # Label ID
        super(ItemsStore, self).__init__(*(base_cols + args), **kwargs)


class SyncObject(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    sync_status = GObject.property(type=object)
    auth = GObject.property(type=GObject.Object)
