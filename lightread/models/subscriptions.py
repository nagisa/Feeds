import os
import json
import hashlib
import random
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
        self.icon_theme = Gtk.IconTheme.get_default()
        self.icon_flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
        self.load_data()

    def sync(self):
        if not self.ensure_login(auth, self.sync):
            return False
        url = utils.api_method('subscription/list')
        msg = utils.AuthMessage(auth, 'GET', url)
        utils.session.queue_message(msg, self.on_response, None)

    def on_response(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['subscriptions']
        cached = {'labels': {}, 'subscriptions': {}}
        for sub in res:
            subid = str(int(sub['sortid'], 16))
            for category in sub['categories']:
                if category['id'] not in cached['labels']:
                    name = category['label']
                    cached['labels'][category['id']] = {'name': name,
                                                        'items': []}
                cached['labels'][category['id']]['items'].append(subid)
            cached['subscriptions'][subid] = {'title': sub['title'],
                                              'id': sub['id'],
                                              'url': sub['htmlUrl']}
            self.favicons.fetch_icon(sub['htmlUrl'])

        with open(os.path.join(CACHE_DIR, 'subscriptions'), 'w') as f:
            json.dump(cached, f)
        self.load_data(cached)

    def _read_data(self):
        with open(os.path.join(CACHE_DIR, 'subscriptions'), 'r') as f:
            return json.load(f)

    def icon_from_url(self, url):
        fpath = self.favicons.cached_icon(url)
        if fpath is None:
            selections = ['image-loading']
        elif os.path.getsize(fpath) > 10:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(fpath, 16, 16)
        else:
            selections = ['application-rss+xml', 'application-atom+xml',
                          'text-html', Gtk.STOCK_FILE]
        icon = self.icon_theme.choose_icon(selections, 16, self.icon_flag)
        if icon is None:
            return None
        else:
            return icon.load_icon()

    def load_data(self, data=None):
        self.emit('pre-clear')
        self.clear()
        items_added = set()
        try:
            if data is None:
                data = self._read_data()
        except IOError:
            return

        # Add items to labels
        for key, label in data['labels'].items():
            favicon = self.icon_theme.load_icon(Gtk.STOCK_DIRECTORY, 16,
                                                self.icon_flag)
            ptr = self.append(None, (favicon, label['name'],))
            for item in label['items']:
                subscription = data['subscriptions'][item]
                favicon = self.icon_from_url(subscription['url'])
                self.append(ptr, (favicon, subscription['title'],))
                items_added.add(item)
        # Add items that are unlabeled
        for item in set(data['subscriptions'].keys()) - items_added:
            subscription = data['subscriptions'][item]
            favicon = self.icon_from_url(subscription['url'])
            self.append(None, (favicon, subscription['title'],))
        self.emit('sync-done')

    def on_icon_update(self, *args):
        for row in self:
            pass

class Favicons(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, (str,))
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.favdir = os.path.join(CACHE_DIR, 'favicons')
        if not os.path.exists(self.favdir):
            os.makedirs(self.favdir)

    def icon_name(self, origin_url):
        fname = hashlib.md5(bytes(origin_url, 'utf-8')).hexdigest()
        return os.path.join(self.favdir, fname)

    def cached_icon(self, origin_url):
        fpath = self.icon_name(origin_url)
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
        fpath = self.icon_name(url)
        if not (200 <= msg.status_code < 400) or msg.status_code == 204:
            logger.warning('Could not get icon for {0}'.format(url))
            open(fpath, 'wb').close()
            return
        with open(fpath, 'wb') as f:
            f.write(msg.response_body.flatten().get_data())
        self.emit('sync-done', fpath)
