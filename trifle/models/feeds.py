# -*- coding:utf-8 -*-
"""
Downloads items from google reader, caches it, gets respective favicons
et cetera
"""
from gi.repository import Soup, GObject, Gtk
if not PY2:
    from urllib.parse import urlencode
else:
    from urllib import urlencode
    import codecs
import ctypes
import json
import os
import re

from models.auth import auth
from models import utils
from models.settings import settings
from views.utils import connect_once


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


class Flags(GObject.Object, utils.LoginRequired):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    flags = {'read': 'user/-/state/com.google/read'}
    syncing = 0

    def set_flag(self, item_id, flag):
        query = 'SELECT COUNT(item_id) FROM flags WHERE item_id=? AND flag=?'
        if not utils.connection.execute(query, (item_id, flag,)).fetchone()[0]:
            # We don't have a flag like this one yet!
            query = 'INSERT INTO flags(item_id, flag) VALUES (?, ?)'
            utils.connection.execute(query, (item_id, flag,))

    def set_read(self, item_id):
        """ Will be used mostly for marking items as read """
        self.set_flag(item_id, self.flags['read'])

    def sync(self):
        if not self.ensure_login(auth, self.sync) or \
           not self.ensure_token(auth, self.sync):
            return False

        uri = utils.api_method('edit-tag')
        req_type = 'application/x-www-form-urlencoded'
        for flag in self.flags.values():
            query = 'SELECT item_id FROM flags WHERE flag=?'
            result = utils.connection.execute(query, (flag,)).fetchall()
            if len(result) == 0:
                continue

            ch = utils.split_chunks((('i', i) for i, in result), 250, ('', ''))
            for chunk in ch:
                self.syncing += 1
                data = urlencode(chunk + (('a', flag), ('T', auth.token),))
                msg = utils.AuthMessage(auth, 'POST', uri)
                msg.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
                utils.session.queue_message(msg, self.on_response, result)

        if self.syncing == 0:
            self.emit('sync-done')

    def on_response(self, session, message, data):
        self.syncing -= 1
        if 400 <= message.status_code < 600 or 0 <= message.status_code < 100:
            logger.error('Flags request returned {0}'
                                                 .format(message.status_code))
            if self.syncing == 0:
                self.emit('sync-done')
            return False

        query = 'DELETE FROM flags WHERE ' + \
                ' OR '.join('item_id=?' for i in data)
        utils.connection.execute(query, tuple(i for i, in data))

        if self.syncing == 0:
            self.emit('sync-done')
            utils.connection.commit()



class Items(Gtk.ListStore, utils.LoginRequired):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_FIRST, None, [])
    }
    html_re = re.compile('<.+?>')
    space_re = re.compile('[\t\n\r]+')

    def __init__(self, *args, **kwargs):
        self.ids = Ids()
        self.flags = Flags()
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

    def process_item(self, item, short_id):
        """
        Should return a dictionary, content pair.
        Dictionary should contain subscription, time, href, author, title and
        summary fields.
        If any of values doesn't exist, they'll be replaced with meaningful
        defaults. For example "Unknown" for author or "Untitled item" for
        title
        """
        # After a lot of fiddling around I realized one thing. We are IN NO
        # WAY guaranteed that any of these fields exists at all.
        # This idiocy should make this method bigger than a manpage for
        # understanding teenage girls' thought processes.
        def strip_html_nl(text):
            text = self.html_re.sub('', text).strip()
            return self.space_re.sub('', text)

        result = {}
        result['unread'] = int(short_id) in self.ids.sets['unread']
        result['starred'] = int(short_id) in self.ids.sets['starred']
        result['subscription'] = item['origin']['streamId']
        result['author'] = utils.unescape(item.get('author', _('Stranger')))
        # How could they even think of putting html into feed title?!
        # L10N Untitled refers to an item without title
        result['title'] = strip_html_nl(item.get('title', _('Untitled')))

        result['time'] = float(item['crawlTimeMsec']) / 1000
        if result['time'] >= item.get('updated', -1):
            result['time'] = item['updated']

        try:
            result['href'] = item['alternate'][0]['href']
        except KeyError:
            result['href'] = item['origin']['htmlUrl']

        content = item['summary']['content'] if 'summary' in item else \
                  item['content']['content'] if 'content' in item else ''
        if len(content) != 0:
            result['summary'] = utils.unescape(strip_html_nl(content)[:1000])
            if len(result['summary']) > 140:
                result['summary'] = result['summary'][:139] + u('…')
        else:
            result['summary'] = ''

        return result, content

    def sync(self):
        if self.syncing > 0:
            logger.warning('Already syncing')
            return
        self.syncing += 2

        def callback(ids, self):
            self.syncing -= 1
            if self.syncing == 1:
                self.ids.sync()
            if self.syncing == 0:
                self.sync2()

        connect_once(self.flags, 'sync-done', callback, self)
        connect_once(self.ids, 'sync-done', callback, self)
        self.flags.sync()

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
        if 400 <= message.status_code < 600 or 0 <= message.status_code < 100:
            logger.error('Chunk request returned {0}'
                                                 .format(message.status_code))
        else:
            data = json.loads(message.response_body.data)
            for item in data['items']:
                sid = self.get_short_id(item['id'])
                metadata, content = self.process_item(item, sid)
                if sid not in self or self.needs_update(sid, item):
                    FeedItem.save_content(sid, content)
                # We need to update metadata no matter what
                self[sid] = metadata

        self.syncing -= 1
        if self.syncing == 0:
            self.collect_garbage()
            utils.connection.commit()
            self.emit('sync-done')

    def collect_garbage(self):
        query = '''SELECT id FROM items WHERE starred=0
                             ORDER BY time DESC LIMIT 5000 OFFSET ?'''
        items = settings['cache-items']
        rows = utils.connection.execute(query, (items,)).fetchall()
        # SQLite doesn't like working on more than 1000 ORs
        query = 'DELETE FROM items WHERE {0}'
        if len(rows) > 0:
            for block in utils.split_chunks(rows, 900, (None,)):
                block = [i for i, in block if i]
                q = query.format(' OR '.join('id=?' for i in block))
                utils.connection.execute(q, tuple(i for i in block))
                for i in block:
                    FeedItem.remove_content(i)

    def compare(self, row1, row2, user_data):
        value1 = self.get_value(row1, 0).time
        value2 = self.get_value(row2, 0).time
        if value1 > value2:
            return 1
        elif value1 == value2:
            return 0
        else:
            return -1

    def set_read(self, item):
        self.flags.set_read(item.item_id)
        query = 'UPDATE items SET unread=0 WHERE id=?'
        utils.connection.execute(query, (item.item_id,))
        utils.connection.commit()
        item.unread = False


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

    @property
    def unread_count(self):
        query = 'SELECT COUNT(id) FROM items WHERE unread=1'
        return utils.connection.execute(query).fetchone()[0]


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
            self.site = r[8]

    @property
    def icon(self):
        return utils.icon_pixbuf(self.origin)

    @staticmethod
    def save_content(item_id, content):
        fpath = os.path.join(content_dir, str(item_id))
        if not PY2:
            with open(fpath, 'w') as f:
                f.write(content)
        else:
            with codecs.open(fpath, 'w', 'utf-8') as f:
                f.write(content)

    @staticmethod
    def remove_content(item_id):
        fpath = os.path.join(content_dir, str(item_id))
        try:
            os.remove(fpath)
        except OSError:
            logger.exception('Could not remove content file')

    @staticmethod
    def read_content(item_id):
        fpath = os.path.join(content_dir, str(item_id))
        if not PY2:
            with open(fpath, 'r') as f:
                return f.read()
        else:
            with codecs.open(fpath, 'r', 'utf-8') as f:
                f.read()
