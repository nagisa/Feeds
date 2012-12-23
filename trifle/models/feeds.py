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
        self.forced = set()

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

        query = '''SELECT I.id, I.title, summary, href, time/1000000, unread,
                   starred, S.url, S.title, S.id, label_id FROM items AS I
                   LEFT JOIN subscriptions AS S ON S.id=I.subscription
                   LEFT JOIN labels_fk AS L ON L.item_id=S.id
                   ORDER BY time DESC'''
        items = utils.sqlite.execute(query).fetchall()
        existing_ids = {r[0]: self.get_iter(key) for key, r in enumerate(self)}
        for item in items:
            cols = list(item)
            if item[0] in existing_ids:
                v = zip(*filter(lambda x: x[1] is not None, enumerate(cols)))
                self.set(existing_ids[item[0]], *v)
            else:
                cols.append(False) # Needed for correct length
                self.append(cols)
        # Remove items we do not have anymore
        for removed_id in set(existing_ids.keys()) - set(i[0] for i in items):
            self.remove(existing_ids[removed_id])

        self.handler_unblock(self.row_ch_handler)
        self.set_sort_column_id(4, Gtk.SortType.DESCENDING)

    def unforce_all(self):
        if len(self.forced) == 0:
            return
        for row in (row for row in self if row[0] in self.forced):
            self.forced.remove(row[0])
            row[11] = False
            if len(self.forced) == 0:
                break

    @staticmethod
    def on_changed(self, path, itr):
        row = self[itr]
        if row[11] == True and row[0] not in self.forced:
            self.forced.add(row[0])
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
