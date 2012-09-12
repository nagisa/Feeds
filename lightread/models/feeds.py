"""
Downloads feeds from google reader, caches it, gets respective favicons
et cetera

Sadly we cannot download a lot of pages simultaneously, however, lucky, we
can process (fe. fetch favicon) them while another page is downloading.

Cache structure in sync. order:
reading-list # Contains ids of all cached items, binary
unread # Contains ids of cached either new or kept unread items, binary
starred # Contains ids of cached starred items
read # Contains ids of cached read items
/items # Contains .json files with metadata of each feed.
/data/content # Content data with embedded images and so on. Compressed
/data/favicons # Favicons of course
"""
import json
import os
import re
import struct
import itertools
import ctypes
from urllib.parse import urlencode
from datetime import datetime
from gi.repository import Soup, GObject, GLib, Gtk

from lightread.models import auth, utils, settings

content_dir = os.path.join(CACHE_DIR, 'content')
if not os.path.exists(content_dir):
    os.makedirs(content_dir)
metadata_dir = os.path.join(CACHE_DIR, 'metadata')
if not os.path.exists(metadata_dir):
    os.makedirs(metadata_dir)


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
        fpath = os.path.join(CACHE_DIR, key)
        if not os.path.isfile(fpath):
            raise KeyError('ID file at {0} does not exist'.format(fpath))
        size = os.path.getsize(fpath)
        if size == 0:
            return frozenset()
        itemsize = struct.calcsize('q')
        if size % itemsize != 0:
            logger.error('File does not have expected filesize')
            return frozenset()
        items = int(size / itemsize)
        with open(fpath, 'rb') as f:
            return frozenset(struct.unpack('>{0}q'.format(items), f.read()))

    def __setitem__(self, key, value):
        """
        Writes ids to a cache. Value expects an iterator yielding signed
        integers up to 64 bits in length
        """
        logger.debug('Writing {0} IDs'.format(key))
        if key not in self.states:
            logger.warning('Key {0} is not in states'.format(key))
        fpath = os.path.join(CACHE_DIR, key)
        items = len(value)
        with open(fpath, 'wb') as f:
            f.write(struct.pack('>{0}q'.format(items), *value))

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
        super(Items, self).__init__(FeedItem, **kwargs)

    def __getitem__(self, key):
        return FeedItem(str(key))

    def __setitem__(self, key, data):
        with open(os.path.join(metadata_dir, key), 'w') as f:
            json.dump(data, f)

    def __contains__(self, key):
        return os.path.isfile(os.path.join(metadata_dir, key))

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
            self.emit('sync-done')

    def process_item(self, item):
        """
        Returns wether object should continue filling cache
        """
        shrt_id = str(ctypes.c_int64(int(item['id'].split('/')[-1], 16)).value)
        if shrt_id in self and self[shrt_id].same_date(item['updated']):
            # It didn't change, no need to change it.
            return
        self[shrt_id], content = self.normalize_item(item)
        self[shrt_id].set_content(content)

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
            result['title'] = self.purge_html.sub('', item['title'])
        else:
            result['title'] = _('Untitled item')

        if 'summary' in item:
            content = item['summary']['content']
        elif 'content' in item:
            content = item['content']['content']
        else:
            content = ""
        result['summary'] = self.purge_html.sub('', content)[:140] + "…"

        return result, content

    def set_category(self, category):
        try:
            self.append_ids(self.ids[category])
        except KeyError:
            # We don't have IDs cached, and can do nothing about it before
            # cache happens.
            return

    def append_ids(self, ids):
        self.clear()
        # Way to make view show filtered items
        for i in ids:
            self.append((self[i],))

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

        fpath = os.path.join(metadata_dir, item_id)
        if os.path.isfile(fpath):
            with open(fpath, 'r') as f:
                data = json.load(f)
        else:
            logger.error('FeedItem with id {0} doesn\'t exist'.format(item_id))
        self.title = data['title']
        self.time = data['time']
        self.summary = data['summary']
        self.icon = None
        self.content = 'blahblab'
        self.site = 'blahblab'
        #self.content = data['content']['content']
        #self.site = data['origin']['title']

    def set_content(self, content):
        fpath = os.path.join(content_dir, self.item_id)
        with open(fpath, 'w') as f:
            f.write(content)

    def same_date(self, timestamp):
        return self.time == timestamp
