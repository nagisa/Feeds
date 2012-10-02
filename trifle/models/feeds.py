# -*- coding:utf-8 -*-
"""
Downloads items from google reader, caches it, gets respective favicons
et cetera
"""
from gi.repository import Soup, GObject, Gtk
if PY2:
    import codecs
import ctypes
import json
import os
import re
import itertools

from models.auth import auth
from models import utils
from models.settings import settings
from models.utils import urlencode
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
            logger.error('IDs are already synchronizing')
            return False
        self.partial_handler = self.connect('partial-sync', self.on_done)

        item_limit = settings['cache-items']
        for name, state in self.states.items():
            getargs = state + [('n', item_limit)]
            url = utils.api_method('stream/items/ids', getargs)
            msg = utils.AuthMessage(auth, 'GET', url)
            utils.session.queue_message(msg, self.on_response, name)
            logger.debug('{0} queued'.format(name))
        # Initially mark everything as deletable and unflag all items.
        # Laten in process items that are still important will be unmarked
        # and reflagged again (in ensure_ids and mark_true)
        utils.connection.execute('UPDATE items SET to_delete=1, unread=0,'
                                                   'starred=0, to_sync=0')

    @staticmethod
    def ensure_ids(ids):
        ids = [(i,) for i in ids]
        query = 'INSERT OR IGNORE INTO items(id) VALUES(?)'
        utils.connection.executemany(query, ids)
        query = 'UPDATE items SET to_delete=0 WHERE id=?'
        utils.connection.executemany(query, ids)

    @staticmethod
    def mark_to_sync(items):
        query = '''SELECT id, update_time FROM items'''
        cached = dict(utils.connection.execute(query).fetchall())
        upd = filter(lambda x: cached.get(x[0], -1) < x[1], items)
        query = 'UPDATE items SET to_sync=1, update_time=? WHERE id=?'
        utils.connection.executemany(query, ((t, i,) for i ,t in upd))

    @staticmethod
    def mark_true(ids, field):
        query = 'UPDATE items SET {0}=1 WHERE id=?'.format(field)
        utils.connection.executemany(query, ((i,) for i in ids))

    def on_response(self, session, msg, data):
        if 400 <= msg.status_code < 600 or 0 <= msg.status_code < 100:
            logger.error('IDs request returned {0}'.format(msg.status_code))
            return False

        res = json.loads(msg.response_body.data)['itemRefs']
        tuples = [(int(i['id']), int(i['timestampUsec']),) for i in res]
        self.ensure_ids(int(i['id']) for i in res)
        self.mark_to_sync(tuples)
        getattr(self, 'on_{0}'.format(data.replace('-', '_')))(tuples)
        self.emit('partial-sync', data)

    def on_unread(self, tuples):
        self.mark_true((i for i, t in tuples), 'unread')

    def on_starred(self, tuples):
        self.mark_true((i for i, t in tuples), 'starred')

    def on_reading_list(self, tuples):
        pass

    @property
    def needs_update(self):
        query = 'SELECT id FROM items WHERE to_sync=1'
        return set(i for i, in utils.connection.execute(query).fetchall())

    @staticmethod
    def on_done(self, key, data=None):
        self.done.add(key)
        if not all(key in self.done for key in self.states.keys()):
            return False

        logger.debug('IDs were successfully synchronized')
        self.disconnect(self.partial_handler)
        delattr(self, 'partial_handler')
        self.done = set()
        utils.connection.commit()
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
            utils.connection.commit()
            self.emit('sync-done')


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
        q = '''UPDATE items SET title=?, author=?, summary=?, href=?,
                                time=?, subscription=?, to_sync=0 WHERE id=?'''
        values = (data['title'], data['author'], data['summary'],
                  data['href'], data['time'], data['subscription'], key)
        utils.connection.execute(q, values)

    @staticmethod
    def get_short_id(item_id):
        if '/' not in item_id:
            # It's probably is not a long id, sorry
            return item_id
        short = ctypes.c_int64(int(item_id.split('/')[-1], 16)).value
        return str(short)

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
        result['subscription'] = item['origin']['streamId']
        result['author'] = utils.unescape(item.get('author', _('Stranger')))
        # How could they even think of putting html into feed title?!
        # L10N Untitled refers to an item without title
        result['title'] = utils.unescape(strip_html_nl(item.get('title',
                                                               _('Untitled'))))

        result['time'] = int(item['timestampUsec'])
        if result['time'] >= int(item.get('updated', -1)) * 1E6:
            result['time'] = item['updated'] * 1E6

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
        ids = self.ids.needs_update
        logger.debug('{0} items needs update'.format(len(ids)))
        split_ids = utils.split_chunks((('i', i) for i in ids), 250, ('', ''))

        for chunk in split_ids:
            self.syncing += 1
            data = urlencode(chunk)
            message = utils.AuthMessage(auth, 'POST', uri)
            message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
            utils.session.queue_message(message, self.process_response, None)
        else:
            self.post_sync()

    def process_response(self, session, message, data=None):
        if 400 <= message.status_code < 600 or 0 <= message.status_code < 100:
            logger.error('Chunk request returned {0}'
                                                 .format(message.status_code))
        else:
            data = json.loads(message.response_body.data)
            for item in data['items']:
                sid = self.get_short_id(item['id'])
                metadata, content = self.process_item(item, sid)
                FeedItem.save_content(sid, content)
                self[sid] = metadata

        self.syncing -= 1
        if self.syncing == 0:
            self.post_sync()

    def post_sync(self):
        self.collect_garbage()
        utils.connection.commit()
        self.emit('sync-done')

    def collect_garbage(self):
        query = 'SELECT id FROM items WHERE to_delete=1'
        res = utils.connection.execute(query).fetchall()
        utils.connection.execute('DELETE FROM items WHERE to_delete=1')
        for i, in res:
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

    def set_category(self, category):
        self.category = category
        query = 'SELECT id FROM items'
        if self.category in ['unread', 'starred']:
            query += ' WHERE items.{0}=1'.format(self.category)
        ids = (_id[0] for _id in utils.connection.execute(query).fetchall())
        self.load_ids(ids)

    def set_filter(self, kind, value):
        if kind == utils.SubscriptionType.LABEL:
            q = '''SELECT items.id FROM labels
                   LEFT JOIN labels_fk ON labels_fk.label_id=labels.id
                   INNER JOIN items ON items.subscription=labels_fk.item_id
                   WHERE labels.id=?'''
        else:
            q = '''SELECT items.id FROM items WHERE items.subscription=?'''
        #Assumes that WHERE statement goes last
        if self.category in ['unread', 'starred']:
            q += ' AND items.{0}=1'.format(self.category)
        ids = utils.connection.execute(q, (value,)).fetchall()
        self.load_ids(i for i, in ids)

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
            self.time = r[4] / 1E6
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
