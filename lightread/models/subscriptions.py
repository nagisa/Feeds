import os
import json
import hashlib
import random
import collections
from gi.repository import Gtk, Soup, GdkPixbuf, GObject

from lightread.models import utils, auth


class Subscriptions(Gtk.TreeStore, utils.LoginRequired):
    __gsignals__ = {
        'pre-clear': (GObject.SignalFlags.RUN_FIRST, None, []),
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(GdkPixbuf.Pixbuf, str)
        self.favicons = Favicons()
        self.favicons.connect('sync-done', self.on_icon_update)
        self.load_data()

    def sync(self):
        if not self.ensure_login(auth, self.sync):
            return False
        url = utils.api_method('subscription/list')
        msg = utils.AuthMessage(auth, 'GET', url)
        utils.session.queue_message(msg, self.on_response, None)

    def on_response(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['subscriptions']
        labels, subs = {}, []
        for subscription in res:
            sortid = int(subscription['sortid'], 16)
            # Add label if they doesn't exist yet
            for label in subscription['categories']:
                if label['id'] not in labels:
                    labels[label['id']] = {'name': label['label'],
                                           'subscriptions': []}
                labels[label['id']]['subscriptions'].append(str(sortid))
            subs.append((sortid, subscription['htmlUrl'],
                         subscription['title'], subscription['id'],))
            self.favicons.fetch_icon(subscription['htmlUrl'])


        utils.connection.execute('DELETE FROM subscriptions')
        utils.connection.execute('DELETE FROM labels')
        q = 'INSERT INTO subscriptions(id, url, title, strid) VALUES (?,?,?,?)'
        utils.connection.executemany(q, subs)
        q = 'INSERT INTO labels(id, name, subscriptions) VALUES (?, ?, ?)'
        itr = ((key, val['name'],','.join(val['subscriptions']),)
               for key, val in labels.items())
        utils.connection.executemany(q, itr)
        utils.connection.commit()
        self.load_data()

    def _read_data(self):
        result = collections.defaultdict(list)
        query = 'SELECT name, subscriptions FROM labels'
        labels = utils.connection.execute(query).fetchall()
        added = set()

        if len(labels) == 0:
            return {}, []

        for label in labels:
            subids = set(label[1].split(','))
            added |= subids
            w = ' OR '.join(('id={0}'.format(id) for id in subids))
            query = 'SELECT url, title FROM subscriptions WHERE {0}'.format(w)
            subs = utils.connection.execute(query).fetchall()
            for url, title in subs:
                result[label[0]].append({'url': url, 'title': title})

        w = ' AND NOT '.join(('id={0}'.format(id) for id in added))
        query = 'SELECT url, title FROM subscriptions WHERE NOT {0}'.format(w)
        subs = utils.connection.execute(query).fetchall()
        return result, [{'url': u, 'title': t} for u, t in subs]

    def load_data(self, data=None):
        self.emit('pre-clear')
        self.clear()
        labeled, unlabeled = self._read_data()
        theme = Gtk.IconTheme.get_default()
        flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
        for label, items in labeled.items():
            favicon = theme.load_icon(Gtk.STOCK_DIRECTORY, 16, flag)
            ptr = self.append(None, (favicon, label,))
            for item in items:
                favicon = utils.icon_pixbuf(item['url'])
                self.append(ptr, (favicon, item['title'],))
        for item in unlabeled:
            favicon = utils.icon_pixbuf(item['url'])
            self.append(None, (favicon, item['title'],))
        self.emit('sync-done')

    def on_icon_update(self, *args):
        self.load_data()


class Favicons(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, (str,))
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        favdir = os.path.join(CACHE_DIR, 'favicons')
        if not os.path.exists(favdir):
            os.makedirs(favdir)

    def cached_icon(self, origin_url):
        fpath = utils.icon_name(origin_url)
        if os.path.isfile(fpath):
            return fpath
        return None

    def fetch_icon(self, origin_url):
        # Resync only 5% of icons in order to not stress server
        if not origin_url.startswith('http') or (self.cached_icon(origin_url)
           and not random.randint(0, 20) == 0):
            return False
        url = 'https://getfavicon.appspot.com/{0}?defaulticon=none'
        msg = utils.Message('GET', url.format(origin_url))
        utils.session.queue_message(msg, self.on_response, origin_url)

    def on_response(self, session, msg, url):
        fpath = utils.icon_name(url)
        if not (200 <= msg.status_code < 400) or msg.status_code == 204:
            logger.warning('Could not get icon for {0}'.format(url))
            open(fpath, 'wb').close()
            return
        with open(fpath, 'wb') as f:
            f.write(msg.response_body.flatten().get_data())
        self.emit('sync-done', fpath)
