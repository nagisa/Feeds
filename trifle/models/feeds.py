# -*- coding:utf-8 -*-
import os
from gi.repository import GObject
from gi.repository import Gtk

from trifle.models import utils, synchronizers
from trifle.models.base import ItemsStore


class Store(ItemsStore):
    def __init__(self, *args, **kwargs):
        # We will use this boolean flag to keep track of forced visibility
        super(Store, self).__init__(GObject.TYPE_BOOLEAN, *args, **kwargs)
        self.forced = []

        if not os.path.exists(utils.content_dir):
            os.makedirs(utils.content_dir)

        self.row_ch_handler = self.connect('row-changed', self.on_changed)

    @staticmethod
    def unread_count():
        query = 'SELECT COUNT(unread) FROM items WHERE unread=1'
        return utils.sqlite.execute(query).fetchone()[0]

    def update(self):
        self.set_sort_column_id(-2, Gtk.SortType.DESCENDING) # Unsorted
        self.handler_block(self.row_ch_handler)

        query = '''SELECT items.id, items.title, summary, href, time,
                   unread, starred, s.url, s.title, s.id, label_id FROM items
                   LEFT JOIN subscriptions AS s ON s.id=items.subscription
                   LEFT JOIN labels_fk ON labels_fk.item_id=s.id
                   ORDER BY time DESC'''
        items = utils.sqlite.execute(query).fetchall()
        existing_ids = {r[0]: key for key, r in enumerate(self)}
        for item in items:
            cols = list(item)
            cols[4] = int(cols[4] // 1E6)
            if item[0] in existing_ids:
                self[existing_ids[item[0]]][1:10] = cols[1:10]
            else:
                cols.append(False)
                self.append(cols)

        self.handler_unblock(self.row_ch_handler)
        self.set_sort_column_id(4, Gtk.SortType.DESCENDING)

    def unforce_all(self):
        for path in self.forced:
            self[self.get_iter(path)][11] = False
        self.forced.clear()

    @staticmethod
    def on_changed(self, path, itr):
        row = self[itr]
        if row[11] == True and path not in self.forced:
            self.forced.append(path.copy())
        query = '''UPDATE items SET unread=?, starred=? WHERE id=?'''
        utils.sqlite.execute(query, (row[5], row[6], row[0],))
        self.add_flag(row[0], synchronizers.Flags.flags['read'], not row[5])
        self.add_flag(row[0], synchronizers.Flags.flags['kept-unread'], row[5])
        self.add_flag(row[0], synchronizers.Flags.flags['starred'], row[6])
        utils.sqlite.commit()

    def add_flag(self, item_id, flag, value):
        query = '''INSERT OR REPLACE INTO flags(item_id, flag, remove, id)
                   VALUES (:id, :flag, :remove,
                   (SELECT id FROM flags WHERE item_id=:id AND flag=:flag))'''
        utils.sqlite.execute(query, {'id': item_id, 'flag': flag,
                                     'remove': not value})
