from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Soup
import itertools
import json
import os
import random

from trifle.models import settings
from trifle.models import base
from trifle.models import itemparse
from trifle.utils import (logger, SubscriptionType, api_method, session,
                          sqlite, StateIds, split_chunks, urlencode, quote,
                          CONTENT_PATH, FAVICON_PATH, split_id, icon_name,
                          Message)
from trifle.utils.async import JobExecutor


class Id(base.SyncObject):
    states = {'reading-list': [('s', 'user/-/state/com.google/reading-list')],
              'unread': [('s', 'user/-/state/com.google/reading-list'),
                         ('xt', 'user/-/state/com.google/read')],
              'starred': [('s', 'user/-/state/com.google/starred')]}

    def __init__(self, *args, **kwargs):
        super(Id, self).__init__(*args, **kwargs)
        self.sync_status = {}
        self.connect('notify::sync-status', self.on_status_change)

    def sync(self):
        if self.sync_status.get('synchronizing', False):
            logger.error('IDs are already being synchronized')
            return False
        self.sync_status['synchronizing'] = True

        item_limit = settings.settings['cache-items']
        for name, state in self.states.items():
            getargs = state + [('n', item_limit)]
            url = api_method('stream/items/ids', getargs)
            msg = self.auth.message('GET', url)
            session.queue_message(msg, self.on_response, name)
        # Initially mark everything as deletable and unflag all items.
        # Laten in process items that are still important will be unmarked
        # and reflagged again.
        query = 'UPDATE items SET to_delete=1, unread=0, starred=0, to_sync=0'
        sqlite.execute(query)

    def on_response(self, session, msg, data):
        status = msg.status_code
        if not 200 <= status < 400:
            logger.error('IDs synchronization failed: {0}'.format(status))
            return False

        res = json.loads(msg.response_body.data)['itemRefs']
        id_list = [(int(i['id']),) for i in res]
        self.ensure_ids(id_list)
        self.set_sync_flag({'update_time': int(i['timestampUsec']),
                            'id': int(i['id'])} for i in res)
        if data in ['unread', 'starred']:
            self.set_flag(data, id_list)

        self.sync_status[data] = True
        GLib.idle_add(self.notify, 'sync-status')

    def ensure_ids(self, id_list):
        # We'll insert any ids we don't yet have in our database
        query = 'INSERT OR IGNORE INTO items(id) VALUES(?)'
        sqlite.executemany(query, id_list)
        # And set to_delete flag to zero for all ids we've got.
        # This way all the items with to_delete flag set are too old.
        query = 'UPDATE items SET to_delete=0 WHERE id=?'
        sqlite.executemany(query, id_list)

    def set_sync_flag(self, items):
        query = '''UPDATE items SET to_sync=1, update_time=:update_time WHERE
                   id=:id AND update_time<:update_time'''
        sqlite.executemany(query, items)

    def set_flag(self, flag, id_list):
        query = 'UPDATE items SET {0}=1 WHERE id=?'.format(flag)
        sqlite.executemany(query, id_list)

    @staticmethod
    def on_status_change(self, gprop):
        if all(self.sync_status.get(key, False) for key in self.states.keys()):
            logger.debug('IDs synchronizaton completed')
            sqlite.commit()
            GLib.idle_add(self.emit, 'sync-done')


class Flags(base.SyncObject):
    def __init__(self, *args, **kwargs):
        super(Flags, self).__init__(*args, **kwargs)
        self.sync_status = 0

    def sync(self):
        if self.sync_status > 0:
            logger.error('Flags are already being synchronized')
            return False
        self.sync_status = 0
        query = 'SELECT item_id, id FROM flags WHERE flag=? AND remove=?'

        for flag, st in itertools.product(StateIds, [True, False]):
            self.sync_status += 1
            sqlite.execute(query, (flag, st)).connect('finished', self.on_data,
                                                      (flag, st))

    def on_data(self, job, success, data):
        flag, st = data
        self.sync_status -= 1
        if not success:
            logger.error('Could not get data from SQLite correctly')
            return

        if not len(job.result) == 0:
            uri = api_method('edit-tag')
            req_type = 'application/x-www-form-urlencoded'

            post = (('r' if st else 'a', flag,), ('T', self.auth.edit_token),)
            chunks = split_chunks(job.result, 250, None)
            for chunk in chunks:
                iids, ids = zip(*filter(lambda x: x is not None, chunk))
                iids = tuple(zip(itertools.repeat('i'), iids))
                payload = urlencode(iids + post)
                msg = self.auth.message('POST', uri)
                msg.set_request(req_type, Soup.MemoryUse.COPY, payload,
                                len(payload))
                session.queue_message(msg, self.on_response, ids)
                self.sync_status += 1

        if self.sync_status == 0:
            # In case we didn't have any flags to synchronize
            logger.debug('There were no flags to synchronize')
            GLib.idle_add(self.emit, 'sync-done')

    def on_response(self, session, message, data):
        self.sync_status -= 1
        if self.sync_status == 0:
            logger.debug('Flags synchronizaton completed')
            GLib.idle_add(self.emit, 'sync-done')

        status = message.status_code
        if not 200 <= status < 400:
            logger.error('Flags synchronizaton failed {0}'.format(status))
            return False

        data = ((i,) for i in data)
        sqlite.executemany('DELETE FROM flags WHERE id=?', data)
        if self.sync_status == 0:
            sqlite.commit()


class Items(base.SyncObject):
    def __init__(self, *args, **kwargs):
        super(Items, self).__init__(*args, **kwargs)
        self.sync_status = 0

    def sync(self):
        if self.sync_status > 0:
            logger.warning('Items are already being synchronized')
            return
        self.sync_status = 0
        logger.debug('Synchronizing items')
        self.dump_garbage()

        job = sqlite.execute('SELECT id FROM items WHERE to_sync=1')
        job.connect('finished', self.on_sync_ids)

    def on_sync_ids(self, job, success):
        if not success:
            logger.error('Could not get data from SQLite')
            return

        if len(job.result) == 0:
            logger.debug('Items doesn\'t need synchronization')
            GLib.idle_add(self.emit, 'sync-done')
            return

        # Somewhy when streaming items and asking more than 512 returns 400.
        # Asking anything in between 250 and 512 returns exactly 250 items.
        chunks = split_chunks((('i', i) for i, in job.result), 250, ('', ''))
        # Asynchronous job queue for items parsing
        # We will, unless we have a bug, have only one synchronization at time
        # thus it is safe to initialize it like that.
        executor = JobExecutor()
        executor.start()

        uri = api_method('stream/items/contents')
        req_type = 'application/x-www-form-urlencoded'
        for chunk in chunks:
            self.sync_status += 1
            data = urlencode(chunk)
            message = self.auth.message('POST', uri)
            message.set_request(req_type, Soup.MemoryUse.COPY, data,
                                len(data))
            session.queue_message(message, self.on_response, executor)
        self.connect('notify::sync-status', self.on_sync_status, executor)

    def on_response(self, session, message, executor):
        status = message.status_code
        if not 200 <= status < 400:
            logger.error('Items synchronization failed {0}'.format(status))
            return

        job = executor.submit(itemparse.process_items,
                              message.response_body.data)
        job.connect('finished', self.on_chunk_parsed, executor)

    def on_chunk_parsed(self, job, success, executor):
        self.sync_status -= 1
        if not success:
            try:
                raise job.exception
            except:
                logger.exception('Failed to parse item chunk')
        else:
            query = '''UPDATE items SET title=:title, author=:author,
                       summary=:summary, href=:href, time=:time,
                       subscription=:subscription WHERE id=:id'''
            sqlite.executemany(query, job.result)

    @staticmethod
    def on_sync_status(self, gprop, executor):
        if self.sync_status != 0:
            return
        sqlite.commit()
        executor.stop()
        GLib.idle_add(self.emit, 'sync-done')
        logger.debug('Items synchronization completed')

    def dump_garbage(self):
        """ Remove all items (and contents) marked with to_delete flag """
        query = 'SELECT id FROM items WHERE to_delete=1'

        def callback(job, success):
            for item_id, in job.result:
                fpath = os.path.join(CONTENT_PATH, str(item_id))
                if os.path.isfile(fpath):
                    os.remove(fpath)
        sqlite.execute(query).connect('finished', callback)
        sqlite.execute('DELETE FROM items WHERE to_delete=1')


class Subscriptions(base.SyncObject):
    __gsignals__ = {
        'subscribed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
        'label-set': (GObject.SignalFlags.RUN_LAST, None, (bool,))
    }

    def sync(self):
        url = api_method('subscription/list')
        msg = self.auth.message('GET', url)
        session.queue_message(msg, self.on_response, None)

    def on_response(self, session, msg, data):
        status = msg.status_code
        if not 200 <= status < 400:
            logger.error('Subscriptions synchronization failed {0}'
                         .format(status))
            return

        # Clear database, it's easier than updating everything ;)
        q = '; DELETE FROM '.join(('subscriptions', 'labels', 'labels_fk'))
        sqlite.executescript('DELETE FROM ' + q)
        res = json.loads(msg.response_body.data)['subscriptions']
        # Some items do not have htmlUrl
        for d in res:
            d.setdefault('htmlUrl')

        # Reinsert items
        q = '''INSERT INTO subscriptions(id, url, title)
               VALUES(:id, :htmlUrl, :title)'''
        sqlite.executemany(q, res)

        lid = lambda x: x['id'].split('/', 2)[-1]
        # Reinsert labels
        q = 'INSERT OR IGNORE INTO labels(id, name) VALUES (?, ?)'
        values = {(lid(l), l['label']) for s in res for l in s['categories']}
        sqlite.executemany(q, values)

        # Estabilish foreign keys via labels_fk
        q = 'INSERT INTO labels_fk(item_id, label_id) VALUES(?, ?)'
        values = ((s['id'], lid(l)) for s in res for l in s['categories'])
        sqlite.executemany(q, values)
        logger.debug('Subscriptions synchronization completed')
        GLib.idle_add(self.emit, 'sync-done')

    def subscribe_to(self, url):
        uri = api_method('subscription/quickadd')
        req_type = 'application/x-www-form-urlencoded'
        data = urlencode({'T': self.auth.edit_token, 'quickadd': url})
        msg = self.auth.message('POST', uri)
        msg.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        session.queue_message(msg, self.on_quickadd, None)

    def on_quickadd(self, session, msg, data=None):
        if not 200 <= msg.status_code < 400:
            logger.error('Add request returned {0}'.format(msg.status_code))
            GLib.idle_add(self.emit, 'subscribed', False)
        res = json.loads(msg.response_body.data)
        GLib.idle_add(self.emit, 'subscribed', 'streamId' in res)

    def set_item_label(self, vals, label_id, value):
        if vals[0] != SubscriptionType.SUBSCRIPTION:
            logger.error('Adding label to non-subscription!')
            return False

        uri = api_method('subscription/edit')
        req_type = 'application/x-www-form-urlencoded'
        label_id = 'user/-/{0}'.format(label_id)
        action = 'a' if value else 'r'
        item_id = split_id(vals[1])[1]
        data = urlencode({'T': self.auth.edit_token, 's': item_id,
                                'ac': 'edit', action: label_id})
        msg = self.auth.message('POST', uri)
        msg.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        session.queue_message(msg, self.on_sub_edit, None)

    def on_sub_edit(self, session, msg, data=None):
        if not 200 <= msg.status_code < 400:
            logger.error('Edit request returned {0}'.format(msg.status_code))
            return False
        GLib.idle_add(self.emit, 'label-set', 200 <= msg.status_code < 400)


class Favicons(base.SyncObject):
    def __init__(self, *args, **kwargs):
        super(Favicons, self).__init__(*args, **kwargs)
        self.sync_status = 0
        if not os.path.exists(FAVICON_PATH):
            os.makedirs(FAVICON_PATH)

    def sync(self):
        query = 'SELECT url FROM subscriptions'
        sqlite.execute(query).connect('finished', self.on_site_uris)

    def on_site_uris(self, job, success):
        uri = 'https://getfavicon.appspot.com/{0}?defaulticon=none'
        for site_uri, in job.result:
            if site_uri is None or not site_uri.startswith('http'):
                continue
            elif self.has_icon(site_uri) and not random.randint(0, 200) == 0:
                # Resync only 0.5% of icons. It's unlikely that icon changes
                # or becomes available
               continue
            msg = Message('GET', uri.format(quote(site_uri)))
            session.queue_message(msg, self.on_response, site_uri)
            self.sync_status += 1
        if self.sync_status == 0:
            logger.debug('Favicons synchronization completed')
            GLib.idle_add(self.emit, 'sync-done')

    def on_response(self, session, msg, site_uri):
        self.sync_status -= 1
        with open(icon_name(site_uri), 'wb') as f:
            if not (200 <= msg.status_code < 400) or msg.status_code == 204:
                logger.warning('Could not get icon for {0}'.format(site_uri))
                # Save an empty file so we know that we don't have an icon
            else:
                f.write(msg.response_body.flatten().get_data())
        if self.sync_status == 0:
            logger.debug('Favicons synchronization completed')
            GLib.idle_add(self.emit, 'sync-done')

    def has_icon(self, site_uri):
        return os.path.isfile(icon_name(site_uri))
