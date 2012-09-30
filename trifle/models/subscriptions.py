from gi.repository import Gtk, GdkPixbuf, GObject, GLib
import json
import os
import random

from models.auth import auth
from models import utils

SubscriptionType = utils.SubscriptionType
class Subscriptions(Gtk.TreeStore, utils.LoginRequired):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, [])
    }

    def __init__(self, *args, **kwargs):
        # SubscriptionType, id for item, icon_fpath, name
        super(Subscriptions, self).__init__(int, str, GdkPixbuf.Pixbuf, str)
        self.favicons = Favicons()
        self.favicons_syncing = 0
        self.favicons.connect('sync-done', self.on_icon_update)
        self.last_update = GLib.get_monotonic_time()
        self.label_iters = {}
        self.sub_iters = {}

    def sync(self):
        if not self.ensure_login(auth, self.sync):
            return False
        url = utils.api_method('subscription/list')
        msg = utils.AuthMessage(auth, 'GET', url)
        utils.session.queue_message(msg, self.on_response, None)

    def on_response(self, session, msg, data=None):
        res = json.loads(msg.response_body.data)['subscriptions']
        subs = []
        lbl_id = lambda x: x.split('/', 2)[-1]

        utils.connection.execute('DELETE FROM labels_fk')
        for sub in res:
            # Insert item
            q = '''INSERT OR REPLACE INTO subscriptions(id, url, title)
                                   VALUES(?, ?, ?)'''
            value = (sub['id'], sub['htmlUrl'], sub['title'].strip())
            utils.connection.execute(q, value)

            # Add labels
            values = ((lbl_id(l['id']), l['label']) for l in sub['categories'])
            q = 'INSERT OR REPLACE INTO labels(id, name) VALUES(?, ?)'
            utils.connection.executemany(q, values)

            # And reestabilish bindings via labels_fk
            values = ((sub['id'], lbl_id(l['id'])) for l in sub['categories'])
            q = 'INSERT INTO labels_fk(item_id, label_id) VALUES(?, ?)'
            utils.connection.executemany(q, values)

            if self.favicons.fetch_icon(sub['htmlUrl']):
                self.favicons_syncing += 1

        utils.connection.commit()
        self.update()

    def update(self):
        theme = Gtk.IconTheme.get_default()
        flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
        q = '''SELECT subscriptions.id, subscriptions.url, subscriptions.title,
                      labels.id, labels.name
               FROM subscriptions
               LEFT JOIN labels_fk ON labels_fk.item_id = subscriptions.id
               LEFT JOIN labels ON labels.id=labels_fk.label_id'''
        result = utils.connection.execute(q).fetchall()
        labeled = filter(lambda x: x[3] is not None, result)

        for subid, suburl, subtitle, lblid, lblname in labeled:
            if lblid not in self.label_iters:
                self.label_iters[lblid] = self.append(None)
            icon = theme.load_icon(Gtk.STOCK_DIRECTORY, 16, flag)
            vals = {0: SubscriptionType.LABEL, 1: lblid, 2: icon, 3: lblname}
            self.set(self.label_iters[lblid], vals)

        for subid, suburl, subtitle, lblid, lblname in result:
            if subid not in self.sub_iters:
                label_iter = self.label_iters.get(lblid, None)
                self.sub_iters[subid] = self.append(label_iter)
            icon = utils.icon_pixbuf(suburl)
            vals = {0: SubscriptionType.SUBSCRIPTION, 1: subid, 2: icon,
                    3: subtitle}
            self.set(self.sub_iters[subid], vals)

        if self.favicons_syncing == 0:
            self.emit('sync-done')

    def on_icon_update(self, favicons, url):
        self.favicons_syncing -= 1
        current = GLib.get_monotonic_time()
        # Update view at most every quarter a second
        if current - self.last_update > 0.25E6 or self.favicons_syncing == 0:
            self.last_update = current
            self.update()


class Favicons(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, (str,))
    }

    def __init__(self, *args, **kwargs):
        super(Favicons, self).__init__(*args, **kwargs)
        favdir = os.path.join(CACHE_DIR, 'favicons')
        if not os.path.exists(favdir):
            os.makedirs(favdir)

    def cached_icon(self, origin_url):
        fpath = utils.icon_name(origin_url)
        if os.path.isfile(fpath):
            return fpath
        return None

    def fetch_icon(self, origin_url):
        # Resync only 0.5% of icons. It's very unlikely that icon changes or
        # becomes available
        if not origin_url.startswith('http') or self.cached_icon(origin_url) \
           and not random.randint(0, 200) == 0:
            return False
        url = 'https://getfavicon.appspot.com/{0}?defaulticon=none'
        msg = utils.Message('GET', url.format(origin_url))
        utils.session.queue_message(msg, self.on_response, origin_url)
        return True

    def on_response(self, session, msg, url):
        fpath = utils.icon_name(url)
        if not (200 <= msg.status_code < 400) or msg.status_code == 204:
            logger.warning('Could not get icon for {0}'.format(url))
            open(fpath, 'wb').close()
        else:
            with open(fpath, 'wb') as f:
                f.write(msg.response_body.flatten().get_data())
        self.emit('sync-done', url)
