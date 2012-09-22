"""
Downloads items from google reader, caches it, gets respective favicons
et cetera
"""
import json
import os
import re
import struct
import ctypes
from urllib.parse import urlencode
from datetime import datetime
from gi.repository import Soup, GObject, GLib, Gtk

from lightread.models import auth, utils, settings
from lightread.views.utils import connect_once


content_dir = os.path.join(CACHE_DIR, 'content')
if not os.path.exists(content_dir):
    os.makedirs(content_dir)


class Ids(GObject.Object, utils.LoginRequired):
    states = {'reading-list': [('s', 'user/-/state/com.google/reading-list')],
              'unread': [('s', 'user/-/state/com.google/reading-list'),
                         ('xt', 'user/-/state/com.google/read')],
              'starred': [('s', 'user/-/state/com.google/starred')]}
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
        'partial-sync': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, *args, **kwargs):
        super(Ids, self).__init__(*args, **kwargs)
        self.done = set()
        self.sets = {'reading-list': set(), 'unread': set(), 'starred': set()}

    def sync(self):
        if not self.ensure_login(auth, self.sync):
            return False
        if hasattr(self, 'partial_handler'):
            logger.warning('Sync already in progress')
            return False
        self.partial_handler = self.connect('partial-sync', self.on_done)

        item_limit = settings['cache-items']
        for name, state in self.states.items():
            getargs = state + [('n', item_limit)]
            url = utils.api_method('stream/items/ids', getargs)
            msg = utils.AuthMessage(auth, 'GET', url)
            cb_func = getattr(self, 'on_{0}'.format(name.replace('-', '_')))
            utils.session.queue_message(msg, cb_func, None)
            logger.debug('{0} queued'.format(name))

    def on_unread(self, session, msg, data=None):
        if 'reading-list' not in self.done:
            # We must filter out items which doesn't exist in reading-list
            def cb(self, key, data):
                data[0](*data[1:])
            args = (self.on_unread, session, msg, data)
            connect_once(self, 'partial-sync', cb, args)
            return False

        res = json.loads(msg.response_body.data)['itemRefs']
        unread = set(int(item['id']) for item in res)
        self.sets['unread'] = unread & self.sets['reading-list']
        self.emit('partial-sync', 'unread')

    def on_starred(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['itemRefs']
        self.sets['starred'] = set(int(item['id']) for item in res)
        self.emit('partial-sync', 'starred')

    def on_reading_list(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['itemRefs']
        self.sets['reading-list'] = set(int(item['id']) for item in res)
        self.emit('partial-sync', 'reading-list')

    @staticmethod
    def on_done(self, key, data=None):
        self.done.add(key)
        for key in self.states.keys():
            if key not in self.done:
                return False

        logger.debug('ID sync was completed successfully')
        self.disconnect(self.partial_handler)
        delattr(self, 'partial_handler')
        self.done = set()
        self.emit('sync-done')


class Items(Gtk.ListStore, utils.LoginRequired):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_FIRST, None, [])
    }

    def __init__(self, *args, **kwargs):
        self.ids = Ids()
        self.purge_html = re.compile('<.+?>|[\n\t\r]')
        self.syncing = 0
        self.source_filter = None
        self.category = None
        super(Items, self).__init__(FeedItem, **kwargs)

    def __getitem__(self, key):
        return FeedItem(key)

    def __setitem__(self, key, data):
        q = '''INSERT OR REPLACE INTO items(id, title, author, summary, href,
                                          time, subscription, unread, starred)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        values = (key, data['title'], data['author'], data['summary'],
                  data['href'], data['time'], data['subscription'],
                  data['unread'], data['starred'])
        utils.connection.execute(q, values)

    def __contains__(self, key):
        q = 'SELECT COUNT(id) FROM items where id=?'
        r = utils.connection.execute(q, (key,))
        return False if r.fetchone() is None else True

    @staticmethod
    def get_short_id(item_id):
        if '/' not in item_id:
            # It's probably is not a long id, sorry
            return item_id
        short = ctypes.c_int64(int(item_id.split('/')[-1], 16)).value
        return str(short)

    @staticmethod
    def needs_update(item_id, item):
        time = float(item['crawlTimeMsec']) / 1000
        if time >= item['updated']:
            time = item['updated']
        q = 'SELECT time FROM items WHERE id = ?'
        result = utils.connection.execute(q, (item_id,)).fetchone()
        if result is None or time > result[0]:
            return True
        return False

    def sync(self):
        if self.syncing > 0:
            logger.warning('Already syncing')
            return
        self.syncing += 1

        def callback(ids, self):
            self.sync2()
            self.syncing -= 1

        connect_once(self.ids, 'sync-done', callback, self)
        return self.ids.sync()

    def sync2(self):
        if not self.ensure_login(auth, self.sync2):
            return False
        uri = utils.api_method('stream/items/contents')
        req_type = 'application/x-www-form-urlencoded'

        # Somewhy when streaming items and asking more than 512 returns 400.
        # Asking anything in between 250 and 512 returns exactly 250 items.
        ids = self.ids.sets['reading-list'] | self.ids.sets['starred']
        split_ids = utils.split_chunks((('i', i) for i in ids), 250, ('', ''))

        for chunk in split_ids:
            self.syncing += 1
            data = urlencode(chunk)
            message = utils.AuthMessage(auth, 'POST', uri)
            message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
            utils.session.queue_message(message, self.process_response, None)

    def process_response(self, session, message, data=None):
        if 400 <= message.status_code < 600:
            logger.error('Chunk request returned {0}'
                                                 .format(message.status_code))
        else:
            data = json.loads(message.response_body.data)
            for item in data['items']:
                sid = self.get_short_id(item['id'])
                if sid not in self or self.needs_update(sid, item):
                    self[sid], content = self.process_item(item, sid)
                    FeedItem.save_content(sid, content)

        self.syncing -= 1
        if self.syncing == 0:
            utils.connection.commit()
            self.emit('sync-done')

    def process_item(self, item, short_id):
        # After a lot of fiddling around I realized one thing. We are IN NO
        # WAY guaranteed that any of these fields exists at all.
        # This idiocy should make this method bigger than a manpage for
        # understanding teenage girls' thought processes.
        """
        Should return a dictionary, content pair.
        Dictionary should contain subscription, time, href, author, title and
        summary fields.
        If any of values doesn't exist, they'll be replaced with meaningful
        defaults. For example "Unknown" for author or "Untitled item" for
        title
        """
        result = {}
        result['unread'] = int(short_id) in self.ids.sets['unread']
        result['starred'] = int(short_id) in self.ids.sets['starred']
        result['subscription'] = item['origin']['streamId']

        result['time'] = float(item['crawlTimeMsec']) / 1000
        if result['time'] >= item['updated']:
            result['time'] = item['updated']

        try:
            result['href'] = item['alternate'][0]['href']
        except KeyError:
            result['href'] = item['origin']['htmlUrl']

        if 'author' in item:
            result['author'] = item['author']
        else:
            result['author'] = _('Unspecified person')

        # How could they even think of putting html into feed title?!
        if 'title' in item:
            result['title'] = utils.unescape(
                                        self.purge_html.sub('', item['title']))
        else:
            result['title'] = _('Untitled item')

        if 'summary' in item:
            content = item['summary']['content'].strip()
        elif 'content' in item:
            content = item['content']['content'].strip()
        else:
            content = result['summary'] = ''
        if len(content) != 0:
            result['summary'] = self.purge_html.sub('', content)[:1000]
            result['summary'] = (utils.unescape(result['summary']) + "…")[:140]

        return result, content

    def compare(self, row1, row2, user_data):
        value1 = self.get_value(row1, 0).time
        value2 = self.get_value(row2, 0).time
        if value1 > value2:
            return 1
        elif value1 == value2:
            return 0
        else:
            return -1


class FilteredItems(Items):

    def __init__(self, *args, **kwargs):
        super(FilteredItems, self).__init__(*args, **kwargs)
        self.category = None

    def category_query(self):
        if self.category == 'reading-list':
            query = 'SELECT id FROM items'
        elif self.category == 'unread':
            query = 'SELECT id FROM items WHERE unread=1'
        elif self.category == 'starred':
            query = 'SELECT id FROM items WHERE starred=1'
        else:
            logger.error('Category {0} doesn\'t exist!'.format(category))
            return None
        return query

    def set_category(self, category):
        self.category = category
        query = self.category_query()
        ids = (_id[0] for _id in utils.connection.execute(query).fetchall())
        self.load_ids(ids)

    def set_filter(self, value):
        if value[:4] != 'feed':
            # We've got a label
            query = 'SELECT subscriptions FROM labels WHERE name=?'
            result = utils.connection.execute(query, (value,)).fetchone()
            subscriptions = result[0].split(';')
        else:
            subscriptions = [value]

        cat_query = self.category_query()
        _filter = ' OR '.join('subscription=?' for i in subscriptions)
        if 'WHERE' in cat_query:
            query = cat_query + ' AND ({0})'.format(_filter)
        else:
            query = cat_query + ' WHERE {0}'.format(_filter)

        result = utils.connection.execute(query, tuple(subscriptions))
        ids = (i[0] for i in result.fetchall())
        self.load_ids(ids)

    def load_ids(self, ids):
        self.clear()
        # Way to make view show filtered items
        for i in ids:
            try:
                self.append((self[i],))
            except ValueError:
                pass


class FeedItem(GObject.Object):

    def __init__(self, item_id):
        self.item_id = item_id
        super(FeedItem, self).__init__()

        q = '''
        SELECT items.title, items.author, items.summary, items.href,
               items.time, items.unread, items.starred,
               subscriptions.url, subscriptions.title
        FROM items LEFT JOIN subscriptions ON
             items.subscription = subscriptions.id WHERE items.id=?
        '''
        r = utils.connection.execute(q, (item_id,)).fetchone()

        if r is None:
            msg = 'FeedItem with id {0} doesn\'t exist'.format(item_id)
            logger.error(msg)
            raise ValueError(msg)
        else:
            self.title = r[0]
            self.author = r[1]
            self.summary = r[2]
            self.href = r[3]
            self.time = r[4]
            self.unread = r[5]
            self.starred = r[6]
            self.origin = r[7]
            self.icon = utils.icon_pixbuf(self.origin)
            self.site = r[8]

    @staticmethod
    def save_content(item_id, content):
        fpath = os.path.join(content_dir, str(item_id))
        with open(fpath, 'w') as f:
            f.write(content)

    @staticmethod
    def read_content(item_id):
        fpath = os.path.join(content_dir, str(item_id))
        with open(fpath, 'r') as f:
            return f.read()
