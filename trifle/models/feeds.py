# -*- coding:utf-8 -*-
import os
from gi.repository import GObject

from trifle.models import utils, synchronizers
from trifle.models.base import ItemsStore


class Store(ItemsStore):
    def __init__(self, *args, **kwargs):
        # We will use this boolean flag to keep track of forced visibility
        super(Store, self).__init__(GObject.TYPE_BOOLEAN, *args, **kwargs)
        self.forced = []

        if not os.path.exists(utils.content_dir):
            os.makedirs(utils.content_dir)

        self.connect('row-changed', self.on_changed)

    @staticmethod
    def unread_count():
        query = 'SELECT COUNT(unread) FROM items WHERE unread=1'
        return utils.sqlite.execute(query).fetchone()[0]

    def load(self):
        query = '''SELECT items.id, items.title, author, summary, href, time,
                   unread, starred, s.url, s.title, s.id, label_id FROM items
                   LEFT JOIN subscriptions AS s ON s.id=items.subscription
                   LEFT JOIN labels_fk ON labels_fk.item_id=s.id
                   ORDER BY time DESC'''
        items = utils.sqlite.execute(query).fetchall()
        for item in items:
            cols = list(item)
            cols[5] = int(cols[5] // 1E6)
            cols.append(False)
            self.append(cols)

    def unforce_all(self):
        for path in self.forced:
            self[self.get_iter(path)][12] = False
        self.forced.clear()

    @staticmethod
    def on_changed(self, path, itr):
        row = self[itr]
        if row[12] == True and path not in self.forced:
            self.forced.append(path.copy())
        query = '''UPDATE items SET unread=?, starred=? WHERE id=?'''
        utils.sqlite.execute(query, (row[6], row[7], row[0],))
        self.add_flag(row[0], synchronizers.Flags.flags['read'], not row[6])
        self.add_flag(row[0], synchronizers.Flags.flags['kept-unread'], row[6])
        self.add_flag(row[0], synchronizers.Flags.flags['starred'], row[7])
        utils.sqlite.commit()

    def add_flag(self, item_id, flag, value):
        query = '''INSERT OR REPLACE INTO flags(item_id, flag, remove, id)
                   VALUES (:id, :flag, :remove,
                   (SELECT id FROM flags WHERE item_id=:id AND flag=:flag))'''
        utils.sqlite.execute(query, {'id': item_id, 'flag': flag,
                                     'remove': not value})
