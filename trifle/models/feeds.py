# -*- coding:utf-8 -*-
from gi.repository import GObject
import os

from trifle.models import utils, synchronizers
from trifle.models.base import Item, ItemsStore


class Store(ItemsStore):
    def __init__(self, *args, **kwargs):
        super(Store, self).__init__(*args, **kwargs)
        self.objects_cache = {}

        if not os.path.exists(utils.content_dir):
            os.makedirs(utils.content_dir)

        self.connect('notify::category', self.category_change)
        self.connect('notify::subscription', self.subscription_change)

    @staticmethod
    def category_change(self, gprop):
        query = 'SELECT {fields} FROM items {join}'
        if self.category in ['unread', 'starred']:
            query += ' WHERE items.{0}=1'.format(self.category)
        query += ' ORDER BY time DESC'
        self.load_from_query(query)

    @staticmethod
    def subscription_change(self, gprop):
        if not self.is_feed:
            query = '''SELECT {fields} FROM items {join} WHERE subscriptions.id
                    IN (SELECT item_id FROM labels_fk WHERE label_id=:lblid)'''
            if self.category in ['unread', 'starred']:
                query += ' AND items.{0}=1'.format(self.category)
            query += ' ORDER BY time DESC'
            self.load_from_query(query, lblid=self.subscription)
        else:
            query = '''SELECT {fields} FROM items {join} WHERE
                    items.subscription=:subscription'''
            if self.category in ['unread', 'starred']:
                query += ' AND items.{0}=1'.format(self.category)
            query += ' ORDER BY time DESC'
            subscription = utils.split_id(self.subscription)[1]
            self.load_from_query(query, subscription=subscription)

    @staticmethod
    def unread_count():
        query = 'SELECT COUNT(unread) FROM items WHERE unread=1'
        return utils.sqlite.execute(query).fetchone()[0]

    def load_from_query(self, query, **binds):
        """ Will load items with query. SELECt query should contain {fields}
        and {join} format fields.
        In the end query will look like this:
        SELECT {fields} FROM items {join} WHERE items.unread=1 """
        fields = '''items.id, items.title, author, summary, href, time, unread,
                    starred, subscriptions.url, subscriptions.title'''
        join = 'LEFT JOIN subscriptions ON subscriptions.id=items.subscription'
        query = query.format(fields=fields, join=join)
        items = utils.sqlite.execute(query, binds).fetchall()
        self.clear()
        for item in items:
            props = {'model': self, 'item_id': item[0], 'title': item[1],
                     'author': item[2], 'summary': item[3],'href': item[4],
                     'time': int(item[5] // 1E6), 'unread': item[6],
                     'starred': item[7], 'origin': item[8], 'site': item[9]}
            if not item[0] in self.objects_cache:
                obj = FeedItem(**props)
                self.objects_cache[item[0]] = obj
            else:
                self.objects_cache[item[0]].set_properties(**props)
            self.append((self.objects_cache[item[0]],))
        self.emit('load-done')

    def redraw_row(self, item=None):
        """ Will notify all rows if item is None """
        # Redraw row, for exaple title will instantly become bold again if
        # item is made unread.
        for row in self:
            if item is None or row[0] == item:
                self.row_changed(row.path, row.iter)


class FeedItem(Item):
    model = GObject.property(type=GObject.Object)
    def __init__(self, unread=False, starred=False, *args, **kwargs):
        self._unread, self._starred = bool(unread), bool(starred)
        super(FeedItem, self).__init__(*args, **kwargs)

    @GObject.property
    def content(self):
        fpath = os.path.join(utils.content_dir, str(self.item_id))
        if os.path.isfile(fpath):
            with open(fpath, 'r') as f:
                return f.read()
        else:
            return None

    unread = GObject.property(lambda self: self._unread)
    starred = GObject.property(lambda self: self._starred)

    @unread.setter
    def unread_change(self, value):
        if self.unread == value:
            return
        self._unread = value

        self.add_flag(synchronizers.Flags.flags['kept-unread'], not value)
        self.add_flag(synchronizers.Flags.flags['read'], value)

        query = 'UPDATE items SET unread=? WHERE id=?'
        utils.sqlite.execute(query, (self.unread, self.item_id,))
        utils.sqlite.commit()
        self.notify('unread')
        self.model.redraw_row(self)

    @starred.setter
    def starred_change(self, value):
        if self._starred == value:
            return
        self._starred = value

        self.add_flag(synchronizers.Flags.flags['starred'], not value)

        query = 'UPDATE items SET starred=? WHERE id=?'
        utils.sqlite.execute(query, (self.starred, self.item_id,))
        utils.sqlite.commit()
        self.notify('starred')

    def add_flag(self, flag, remove):
        query = '''INSERT OR REPLACE INTO flags(item_id, flag, remove, id)
                   VALUES (:id, :flag, :remove,
                   (SELECT id FROM flags WHERE item_id=:id AND flag=:flag))'''
        utils.sqlite.execute(query, {'id': self.item_id, 'flag': flag,
                                     'remove': remove})

    def is_presentable(self):
        return not (self.title is None or self.summary is None)
