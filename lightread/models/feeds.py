"""
Downloads items from google reader, caches it, gets respective favicons
et cetera
"""
import json
import os
import re
import struct
import itertools
import ctypes
from urllib.parse import urlencode
from html.entities import name2codepoint
from datetime import datetime
from gi.repository import Soup, GObject, GLib, Gtk

from lightread.models import auth, utils, settings


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

    def __getitem__(self, key):
        """
        Reads its from a cache file. Returns a set with signed 64bit integers
        """
        logger.debug('Reading {0} IDs'.format(key))
        q = 'SELECT id FROM {0}_ids'.format(key.replace('-', '_'))
        resp = utils.connection.execute(q)
        return frozenset(row[0] for row in resp.fetchall())

    def __setitem__(self, key, value):
        """
        Writes ids to a cache. Value expects an iterator yielding signed
        integers up to 64 bits in length
        """
        logger.debug('Writing {0} IDs'.format(key))
        key = key.replace('-', '_')
        utils.connection.execute('DELETE FROM {0}_ids'.format(key))
        q = 'INSERT INTO {0}_ids(id) values(?)'.format(key)
        utils.connection.executemany(q, ((i,) for i in value))
        utils.connection.commit()

    def sync(self):
        if not self.ensure_login(auth, self.sync):
            return False
        if hasattr(self, 'partial_handler'):
            logger.warning('Sync already in progress')
            return False
        self.partial_handler = self.connect('partial-sync', Ids.on_done)

        item_limit = settings['cache-items']
        for name, state in self.states.items():
            getargs = state + [('n', item_limit)]
            url = utils.api_method('stream/items/ids', getargs)
            msg = utils.AuthMessage(auth, 'GET', url)
            cb_func = getattr(self, 'on_{0}'.format(name.replace('-', '_')))
            utils.session.queue_message(msg, cb_func, None)
            logger.debug('{0} queued'.format(name))

    def split(self, ids, chunk_size):
        args = [iter(ids)] * chunk_size
        return itertools.zip_longest(*args, fillvalue=('', ''))

    def on_unread(self, session, msg, data=None):
        if 'reading-list' not in self.done:
            # We must filter out items which doesn't exist in reading-list
            def cb(self, key, data):
                self.disconnect(self._unread_cb)
                delattr(self, '_unread_cb')
                data[0](*data[1:])
            args = (self.on_unread, session, msg, data)
            self._unread_cb = self.connect('partial-sync', cb, args)
            return False

        res = json.loads(msg.response_body.data)['itemRefs']
        unread = set(int(item['id']) for item in res)
        self['unread'] = unread & self['reading-list']
        self.emit('partial-sync', 'unread')

    def on_starred(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['itemRefs']
        self['starred'] = set(int(item['id']) for item in res)
        self.emit('partial-sync', 'starred')

    def on_reading_list(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['itemRefs']
        self['reading-list'] = set(int(item['id']) for item in res)
        self.emit('partial-sync', 'reading-list')

    def on_done(self, key, data=None):
        self.done.add(key)
        for key in self.states.keys():
            if key not in self.done:
                return False

        logger.debug('Sync was completed successfully')
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
        utils.connection.execute('DELETE FROM items WHERE id=?', (key,))
        q = 'INSERT INTO items(id, title, author, summary, href, time, ' \
            'origin_id) VALUES (?, ?, ?, ?, ?, ?, ?)'
        values = (key, data['title'], data['author'], data['summary'],
                  data['href'], data['time'], data['origin'])
        utils.connection.execute(q, values)

    def __contains__(self, key):
        q = 'SELECT COUNT(id) FROM items where id=?'
        r = utils.connection.execute(q, (key,))
        return False if r.fetchone() is None else True

    def sync(self):
        if self.syncing > 0:
            logger.warning('Already syncing')
            return
        self.syncing += 1
        def callback(ids, self):
            ids.disconnect(self.ids_handler)
            self.sync2()
            self.syncing -= 1
        self.ids_handler = self.ids.connect('sync-done', callback, self)
        return self.ids.sync()

    def sync2(self):
        if not self.ensure_login(auth, self.sync2):
            return False
        url = utils.api_method('stream/items/contents')
        req_type = 'application/x-www-form-urlencoded'
        # Somewhy when streaming items and asking more than 512 returns 400 status code.
        # Asking anything in between 250 and 512 returns exactly 250 items.
        ids = self.ids['reading-list'] | self.ids['starred']
        sd = self.ids.split((('i', i) for i in ids), 250)
        for varlist in sd:
            self.syncing += 1
            data = urlencode(varlist)
            message = utils.AuthMessage(auth, 'POST', url)
            message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
            utils.session.queue_message(message, self.process_response, None)

    def process_response(self, session, message, data=None):
        self.syncing -= 1
        if 400 <= message.status_code < 600:
            logger.error('Chunk request returned {0}'
                                                 .format(message.status_code))
            return False
        data = json.loads(message.response_body.data)
        [self.process_item(item) for item in data['items']]
        if self.syncing == 0:
            utils.connection.commit()
            self.emit('sync-done')

    def process_item(self, item):
        """
        Returns wether object should continue filling cache
        """
        shrt_id = str(ctypes.c_int64(int(item['id'].split('/')[-1], 16)).value)
        try:
            if shrt_id in self and self[shrt_id].same_date(item['updated']):
                # It didn't change, no need to change it.
                return
        except ValueError:
            pass
        self[shrt_id], content = self.normalize_item(item)
        FeedItem.save_content(shrt_id, content)


    def normalize_item(self, item):
        # After a lot of fiddling around I realized one thing. We are IN NO
        # WAY guaranteed that any of these fields exists at all.
        # This idiocy should make this method bigger than a manpage for
        # understanding teenage girls' thought processes.
        """
        Should return a dictionary, content pair with these items in dict:
        * updated – when the item was last updated
        * origin – where item comes from
        * href – where to direct user for full article. Source.
        * author – who has written this item.
        * summary – content stripped of html and trimmed to 139 characters
        * title

        If any of values doesn't exist, they'll be replaced with meaningful
        defaults. For example "Incognito" for author or "Untitled item" for
        title
        """
        def unescape(string):
            for entity, value in name2codepoint.items():
                if 'amp' == entity:
                    continue
                string = string.replace('&{0};'.format(entity), chr(value))
            string.replace('&amp;', '&')
            return string

        result = {}
        # The only keys that are guaranteed to exist, at least to my knowledge
        result['origin'] = item['origin']['streamId']
        result['time'] = float(item['crawlTimeMsec']) / 1000
        try:
            result['href'] = item['alternate'][0]['href']
        except KeyError:
            result['href'] = result['origin']

        if 'author' in item:
            result['author'] = item['author']
        else:
            result['author'] = _('Incognito')

        # How could they even think of putting html into title?!
        if 'title' in item:
            result['title'] = unescape(self.purge_html.sub('', item['title']))
        else:
            result['title'] = _('Untitled item')

        if 'summary' in item:
            content = item['summary']['content']
        elif 'content' in item:
            content = item['content']['content']
        else:
            content = ""
        result['summary'] = unescape(self.purge_html.sub('', content))[:140]
        result['summary'] += "…"

        return result, content

    def set_category(self, category):
        self.source_filter = None
        try:
            self.set_ids(self.ids[category])
        except KeyError:
           # We don't have IDs cached, and can do nothing about it before
           # cache happens.
            return

    def set_feed_filter(self, value):
        if value[:4] == 'feed':
            self.source_filter = [value]
            self.set_filtered_ids()
            return
        # We have a label
        q = 'SELECT subscriptions FROM labels WHERE name=?'
        r = utils.connection.execute(q, (value,)).fetchone()
        if r is None:
            self.source_filter = []
            self.set_filtered_ids()
            return
        f = ' OR '.join('id={0}'.format(i) for i in r[0].split(','))
        q = 'SELECT strid FROM subscriptions WHERE {0}'.format(f)
        r = utils.connection.execute(q).fetchall()
        self.source_filter = [i[0] for i in r]
        self.set_filtered_ids()

    def set_filtered_ids(self):
        f = ' OR '.join('origin_id=?' for i in self.source_filter)
        q = 'SELECT id FROM items WHERE {0}'.format(f)
        r = utils.connection.execute(q, self.source_filter).fetchall()
        self.set_ids(i[0] for i in r)


    def set_ids(self, ids):
        self.clear()
        # Way to make view show filtered items
        for i in ids:
            try:
                self.append((self[i],))
            except ValueError:
                pass

    def compare(self, row1, row2, user_data):
        value1 = self.get_value(row1, 0).time
        value2 = self.get_value(row2, 0).time
        if value1 > value2:
            return 1
        elif value1 == value2:
            return 0
        else:
            return -1

class FeedItem(GObject.Object):

    def __init__(self, item_id):
        self.item_id = item_id
        super(FeedItem, self).__init__()

        q = '''
        SELECT items.title, items.author, items.summary, items.href,
               items.time, subscriptions.url, subscriptions.title
        FROM items LEFT JOIN subscriptions ON
                items.origin_id = subscriptions.strid WHERE items.id=?
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
            self.origin = r[5]
            self.icon = utils.icon_pixbuf(r[5])
            self.site = r[6]

    def same_date(self, timestamp):
        return self.time == timestamp

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
