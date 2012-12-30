# -*- coding:utf-8 -*-
import os
from gi.repository import GObject
from gi.repository import Gtk

from trifle.models import synchronizers
from trifle.utils import ItemsColumn as Col, CONTENT_PATH, sqlite, StateIds


class Store(Gtk.ListStore):
    def __init__(self, *args, **kwargs):
        cols = (object, # Item ID
                GObject.TYPE_STRING, # Title
                GObject.TYPE_STRING, # Summary
                GObject.TYPE_STRING, # Link to document
                GObject.TYPE_UINT64, # Timestamp
                GObject.TYPE_BOOLEAN, # Is item unread
                GObject.TYPE_BOOLEAN, # Is item starred
                GObject.TYPE_STRING, # Subscription URI
                GObject.TYPE_STRING, # Subscription Title
                GObject.TYPE_STRING, # Subscription ID
                GObject.TYPE_STRING, # Label ID
                GObject.TYPE_BOOLEAN) # Forced visibility
        super(Store, self).__init__(*(cols + args), **kwargs)
        # Items with forced visibility
        self.forced = set()

        if not os.path.exists(CONTENT_PATH):
            os.makedirs(CONTENT_PATH)

        self.row_ch_handler = self.connect('row-changed', self.on_changed)

    @staticmethod
    def unread_count():
        query = 'SELECT COUNT(unread) FROM items WHERE unread=1'
        return sqlite.execute(query).fetchone()[0]

    def update(self):
        self.set_sort_column_id(-2, Gtk.SortType.DESCENDING) # Unsorted
        self.handler_block(self.row_ch_handler)

        query = '''SELECT I.id, I.title, summary, href, time/1000000, unread,
                   starred, S.url, S.title, S.id, label_id FROM items AS I
                   LEFT JOIN subscriptions AS S ON S.id=I.subscription
                   LEFT JOIN labels_fk AS L ON L.item_id=S.id
                   ORDER BY time DESC'''
        items = sqlite.execute(query).fetchall()
        exists = {r[Col.ID]: self.get_iter(key) for key, r in enumerate(self)}
        for item in items:
            if item[0] in exists:
                v = zip(*filter(lambda x: x[1] is not None, enumerate(item)))
                self.set(exists[item[Col.ID]], *v)
            else:
                self.append(item + (False,))
        # Remove items we do not have anymore
        for removed_id in set(exists.keys()) - set(i[Col.ID] for i in items):
            self.remove(exists[removed_id])

        self.handler_unblock(self.row_ch_handler)
        self.set_sort_column_id(Col.TIMESTAMP, Gtk.SortType.DESCENDING)

    def unforce_all(self):
        if len(self.forced) == 0:
            return
        for row in (row for row in self if row[Col.ID] in self.forced):
            self.forced.remove(row[Col.ID])
            row[Col.FORCE_VISIBLE] = False
            if len(self.forced) == 0:
                break

    @staticmethod
    def on_changed(self, path, itr):
        row = self[itr]
        if row[Col.FORCE_VISIBLE] == True:
            self.forced.add(row[Col.ID])
        query = '''UPDATE items SET unread=?, starred=? WHERE id=?'''
        sqlite.execute(query, (row[Col.UNREAD], row[Col.STARRED],
                                     row[Col.ID],))
        self.add_flag(row[0], StateIds.READ, not row[Col.UNREAD])
        self.add_flag(row[0], StateIds.KEPT_UNREAD, row[Col.UNREAD])
        self.add_flag(row[0], StateIds.STARRED, row[Col.STARRED])
        sqlite.commit()

    def add_flag(self, item_id, flag, value):
        query = '''INSERT OR REPLACE INTO flags(item_id, flag, remove, id)
                   VALUES (:id, :flag, :remove,
                   (SELECT id FROM flags WHERE item_id=:id AND flag=:flag))'''
        sqlite.execute(query, {'id': item_id, 'flag': flag,
                                     'remove': not value})
