# -*- coding:utf-8 -*-
"""
Downloads items from google reader, caches it, gets respective favicons
et cetera
"""
from gi.repository import Soup, GObject, Gtk
import ctypes
import itertools
import json
import os
import re

from models import utils
from models.auth import auth
from models.settings import settings
from models.utils import urlencode
from views.utils import connect_once


class Ids(GObject.Object):
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
        if hasattr(self, 'partial_handler'):
            logger.error('IDs are already synchronizing')
            return False
        self.partial_handler = self.connect('partial-sync', self.on_done)
        logger.debug('Synchronizing ids')

        item_limit = settings['cache-items']
        for name, state in self.states.items():
            getargs = state + [('n', item_limit)]
            url = utils.api_method('stream/items/ids', getargs)
            msg = auth.message('GET', url)
            utils.session.queue_message(msg, self.on_response, name)
        # Initially mark everything as deletable and unflag all items.
        # Laten in process items that are still important will be unmarked
        # and reflagged again (in ensure_ids and mark_true)
        utils.sqlite.execute('UPDATE items SET to_delete=1, unread=0,'
                                                   'starred=0, to_sync=0')

    @staticmethod
    def ensure_ids(ids):
        ids = [(i,) for i in ids]
        query = 'INSERT OR IGNORE INTO items(id) VALUES(?)'
        utils.sqlite.executemany(query, ids)
        query = 'UPDATE items SET to_delete=0 WHERE id=?'
        utils.sqlite.executemany(query, ids)

    @staticmethod
    def mark_to_sync(items):
        query = '''SELECT id, update_time FROM items'''
        cached = dict(utils.sqlite.execute(query).fetchall())
        upd = filter(lambda x: cached.get(x[0], -1) < x[1], items)
        query = 'UPDATE items SET to_sync=1, update_time=? WHERE id=?'
        utils.sqlite.executemany(query, ((t, i,) for i ,t in upd))

    @staticmethod
    def mark_true(ids, field):
        query = 'UPDATE items SET {0}=1 WHERE id=?'.format(field)
        utils.sqlite.executemany(query, ((i,) for i in ids))

    def on_response(self, session, msg, data):
        if not 200 <= msg.status_code < 300:
            logger.error('IDs synchronization failed: {0}'
                                                     .format(msg.status_code))
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
        return set(i for i, in utils.sqlite.execute(query).fetchall())

    @staticmethod
    def on_done(self, key, data=None):
        self.done.add(key)
        if not all(key in self.done for key in self.states.keys()):
            return False

        logger.debug('IDs synchronized')
        self.disconnect(self.partial_handler)
        delattr(self, 'partial_handler')
        self.done = set()
        utils.sqlite.commit()
        self.emit('sync-done')


class Flags(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }
    flags = {'read': 'user/-/state/com.google/read',
             'kept-unread': 'user/-/state/com.google/kept-unread',
             'starred': 'user/-/state/com.google/starred'}
    __getitem__ = flags.__getitem__

    def set_flag(self, item_id, flag, remove=False):
        query = 'SELECT remove FROM flags WHERE item_id=? AND flag=?'
        args = (item_id, flag,)
        result = utils.sqlite.execute(query, args).fetchone()

        if result is None:
            # We don't have a flag like this one yet!
            query = 'INSERT INTO flags(item_id, flag, remove) VALUES (?, ?, ?)'
            utils.sqlite.execute(query, args + (remove,))
        elif result[0] != remove:
            query = 'UPDATE flags SET remove=? WHERE item_id=? AND flag=?'
            utils.sqlite.execute(query, (remove,) + args)

    def sync(self):
        self.syncing = 0
        logger.debug('Synchronizing flags')

        uri = utils.api_method('edit-tag')
        req_type = 'application/x-www-form-urlencoded'
        query = 'SELECT item_id, id FROM flags WHERE flag=? AND remove=?'

        for flag in self.flags.values():
            for args in [(flag, True,), (flag, False,)]:
                result = utils.sqlite.execute(query, args).fetchall()
                if len(result) == 0:
                    continue

                post = (('r' if args[1] else 'a', flag,),
                        ('T', auth.edit_token),)
                chunks = utils.split_chunks(result, 250, None)
                for chunk in chunks:
                    self.syncing += 1
                    iids, ids = zip(*filter(lambda x: x is not None, chunk))
                    iids = tuple(zip(itertools.repeat('i'), iids))
                    payload = urlencode(iids + post)
                    msg = auth.message('POST', uri)
                    msg.set_request(req_type, Soup.MemoryUse.COPY, payload,
                                    len(payload))

                    utils.session.queue_message(msg, self.on_response, ids)

        if self.syncing == 0:
            # In case we didn't have any flags to synchronize
            logger.debug('There was no flags to synchronize')
            self.emit('sync-done')

    def on_response(self, session, message, data):
        self.syncing -= 1
        if not 200 <= message.status_code < 400:
            logger.error('Flags synchronizaton failed {0}'
                                                 .format(message.status_code))
            if self.syncing == 0:
                self.emit('sync-done')
            return False

        data = list(data)
        query = 'DELETE FROM flags WHERE ' + \
                ' OR '.join('id=?' for i in data)
        utils.sqlite.execute(query, data)

        if self.syncing == 0:
            utils.sqlite.commit()
            logger.debug('Flags synchronized')
            self.emit('sync-done')


class Items(Gtk.ListStore):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_FIRST, None, [])
    }
    html_re = re.compile('<.+?>')
    space_re = re.compile('[\t\n\r]+')

    def __init__(self, *args, **kwargs):
        if not os.path.exists(utils.content_dir):
            os.makedirs(utils.content_dir)

        self.ids = Ids()
        self.flags = Flags()
        self.syncing = 0
        self.source_filter = None
        self.category = None
        super(Items, self).__init__(FeedItem, **kwargs)

    def __getitem__(self, key):
        return FeedItem(self, key)

    def __setitem__(self, key, data):
        # Row creation should be handled by IDs synchronization
        q = '''UPDATE items SET title=?, author=?, summary=?, href=?,
                                time=?, subscription=?, to_sync=0 WHERE id=?'''
        values = (data['title'], data['author'], data['summary'],
                  data['href'], data['time'], data['subscription'], key)
        utils.sqlite.execute(q, values)

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
                result['summary'] = result['summary'][:139] + '…'
        else:
            result['summary'] = ''

        return result, content

    def sync(self):
        if self.syncing > 0:
            logger.warning('Items synchronization is already in progress')
            return

        self.syncing = 2
        def flags_callback(flags, self):
            self.syncing -= 1
            self.ids.sync()

        def ids_callback(ids, self):
            self.syncing -= 1
            self.sync_items()

        connect_once(self.flags, 'sync-done', flags_callback, self)
        connect_once(self.ids, 'sync-done', ids_callback, self)
        self.flags.sync()

    def sync_items(self):
        logger.debug('Synchronizing items')
        uri = utils.api_method('stream/items/contents')
        req_type = 'application/x-www-form-urlencoded'

        # Somewhy when streaming items and asking more than 512 returns 400.
        # Asking anything in between 250 and 512 returns exactly 250 items.
        ids = self.ids.needs_update
        if len(ids) == 0:
            logger.debug('Items doesn\'t need synchronization')
            self.post_sync()
            return False

        chunks = utils.split_chunks((('i', i) for i in ids), 250, ('', ''))
        for chunk in chunks:
            self.syncing += 1
            data = urlencode(chunk)
            message = auth.message('POST', uri)
            message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
            utils.session.queue_message(message, self.process_response, None)

    def process_response(self, session, message, data=None):
        if not 200 <= message.status_code < 400:
            logger.error('Items synchronization failed: {0}'
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
            logger.debug('Items synchronized')
            self.post_sync()

    def post_sync(self):
        self.collect_garbage()
        utils.sqlite.commit()
        self.emit('sync-done')

    def collect_garbage(self):
        query = 'SELECT id FROM items WHERE to_delete=1'
        res = utils.sqlite.execute(query).fetchall()
        utils.sqlite.execute('DELETE FROM items WHERE to_delete=1')
        for i, in res:
            FeedItem.remove_content(i)

class FilteredItems(Items):

    def __init__(self, *args, **kwargs):
        super(FilteredItems, self).__init__(*args, **kwargs)
        self.category = None

    def category_ids(self, category):
        self.category = category
        query = 'SELECT id FROM items'
        if self.category in ['unread', 'starred']:
            query += ' WHERE items.{0}=1'.format(self.category)
        return (_id[0] for _id in utils.sqlite.execute(query).fetchall())

    def filter_ids(self, kind, value):
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
        ids = utils.sqlite.execute(q, (value,)).fetchall()
        return (i for i, in ids)

    def load_ids(self, ids):
        self.clear()
        # Use python sorting instead of inner ListStore sorting method,
        # because ListStore tries sorting everything after every added item,
        # while now we sort everything in one go
        sorted_ids = sorted((self[i] for i in ids), key=(lambda x: x.time),
                            reverse=True)
        for item in sorted_ids:
            self.append((item,))

    @property
    def unread_count(self):
        query = 'SELECT COUNT(id) FROM items WHERE unread=1'
        return utils.sqlite.execute(query).fetchone()[0]


class FeedItem(GObject.Object):

    def __init__(self, collection, item_id):
        self.item_id = item_id
        self.flags = collection.flags
        self.fetched = False
        self.cache = {}
        super(FeedItem, self).__init__()


    def __getitem__(self, key):
        if not self.fetched:
            q = '''
            SELECT items.title, items.author, items.summary, items.href,
                   items.time, items.unread, items.starred,
                   subscriptions.url, subscriptions.title
            FROM items LEFT JOIN subscriptions ON
                 items.subscription = subscriptions.id WHERE items.id=?
            '''
            r = utils.sqlite.execute(q, (self.item_id,)).fetchone()
            if r is None:
                msg = 'FeedItem with id {0} doesn\'t exist'.format(item_id)
                logger.error(msg)
                raise ValueError(msg)
            self.cache = {'title': r[0], 'author': r[1], 'summary': r[2],
                          'href': r[3], 'time': int(r[4] / 1E6),
                          'unread': r[5], 'starred': r[6], 'origin': r[7],
                          'site': r[7]}
            self.fetched = True

        return self.cache[key]

    def __setitem__(self, key, val):
        self.cache[key] = val
        self.notify(key)

    title = GObject.property(lambda self: self['title'])
    author = GObject.property(lambda self: self['author'])
    summary = GObject.property(lambda self: self['summary'])
    href = GObject.property(lambda self: self['href'])
    time = GObject.property(lambda self: self['time'])
    unread = GObject.property(lambda self: self['unread'])
    starred = GObject.property(lambda self: self['starred'])
    origin = GObject.property(lambda self: self['origin'])
    site = GObject.property(lambda self: self['site'])
    icon = GObject.property(lambda self: utils.icon_pixbuf(self.origin))

    @staticmethod
    def save_content(item_id, content):
        fpath = os.path.join(utils.content_dir, str(item_id))
        with open(fpath, 'w') as f:
            f.write(content)

    @staticmethod
    def remove_content(item_id):
        fpath = os.path.join(utils.content_dir, str(item_id))
        try:
            os.remove(fpath)
        except OSError:
            logger.exception('Could not remove content file')

    @staticmethod
    def read_content(item_id):
        fpath = os.path.join(utils.content_dir, str(item_id))
        with open(fpath, 'r') as f:
            return f.read()

    def set_read(self):
        self.flags.set_flag(self.item_id, self.flags['read'])
        query = 'UPDATE items SET unread=0 WHERE id=?'
        utils.sqlite.execute(query, (self.item_id,))
        utils.sqlite.commit()
        self['unread'] = False
        self.notify('unread')

    def set_keep_unread(self, value):
        self.flags.set_flag(self.item_id, self.flags['read'], remove=value)
        self.flags.set_flag(self.item_id, self.flags['kept-unread'])
        query = 'UPDATE items SET unread=? WHERE id=?'
        utils.sqlite.execute(query, (value, self.item_id,))
        utils.sqlite.commit()
        self['unread'] = value
        self.notify('unread')

    def set_star(self, value):
        self.flags.set_flag(self.item_id, self.flags['starred'],
                            remove=not value)
        query = 'UPDATE items SET starred=? WHERE id=?'
        utils.sqlite.execute(query, (value, self.item_id,))
        utils.sqlite.commit()
        self['starred'] = value
        self.notify('starred')

