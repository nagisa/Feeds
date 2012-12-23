from gi.repository import GObject


class SyncObject(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    sync_status = GObject.property(type=object)
    auth = GObject.property(type=GObject.Object)
