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
        # Icon pixbuf, name, id
        super().__init__(GdkPixbuf.Pixbuf, str, str)
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
        label_query = 'SELECT name, subscriptions FROM labels'
        s_iquery = 'SELECT url, title, strid FROM subscriptions WHERE {0}'
        s_xquery = 'SELECT url, title, strid FROM subscriptions WHERE NOT ({0})'

        result = collections.defaultdict(list)
        labels = utils.connection.execute(label_query).fetchall()
        added = set()

        for label in labels:
            subids = set(label[1].split(','))
            added |= subids
            _filter = ' OR '.join('id={0}'.format(id) for id in subids)
            query = s_iquery.format(_filter)
            for url, title, i in utils.connection.execute(query).fetchall():
                result[label[0]].append({'url': url, 'title': title, 'id': i})

        _filter = ' OR '.join('id={0}'.format(id) for id in added)
        subs = utils.connection.execute(s_xquery.format(_filter)).fetchall()
        return result, [{'url': u, 'title': t, 'id': i} for u, t, i in subs]

    def load_data(self, data=None):
        self.emit('pre-clear')
        self.clear()
        labeled, unlabeled = self._read_data()
        theme = Gtk.IconTheme.get_default()
        flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
        for label, items in labeled.items():
            favicon = theme.load_icon(Gtk.STOCK_DIRECTORY, 16, flag)
            ptr = self.append(None, (favicon, label, label,))
            for item in items:
                favicon = utils.icon_pixbuf(item['url'])
                self.append(ptr, (favicon, item['title'], item['id'],))
        for item in unlabeled:
            favicon = utils.icon_pixbuf(item['url'])
            self.append(None, (favicon, item['title'], item['id'],))
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
