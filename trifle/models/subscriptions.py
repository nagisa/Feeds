from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Soup
import json
import os
import random

from models.auth import auth
from models import utils
from models.utils import SubscriptionType
from utils import logger


class Subscriptions(Gtk.TreeStore):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, []),
        'subscribed': (GObject.SignalFlags.RUN_LAST, None, (bool,))
    }

    def __init__(self, *args, **kwargs):
        # SubscriptionType, id for item, icon_fpath, name
        super(Subscriptions, self).__init__(int, str, GdkPixbuf.Pixbuf, str)
        self.favicons = Favicons()
        self.favicons_syncing = 0
        self.favicons.connect('sync-done', self.on_icon_update)
        self.last_update = GLib.get_monotonic_time()

    @property
    def labels(self):
        return filter(lambda x: x[0] == SubscriptionType.LABEL, self)

    @property
    def subscriptions(self):
        def subs():
            """ Yields all subscriptions in model, including those under
            labels"""
            for item in list(self):
                if item[0] == SubscriptionType.SUBSCRIPTION:
                    yield item
                else:
                    for sub in item.iterchildren():
                        yield sub

        return filter(lambda x: x[0] == SubscriptionType.SUBSCRIPTION, subs())

    @staticmethod
    def combine_ids(label_id, sub_id):
        return sub_id if not label_id else label_id + '/' + sub_id

    @staticmethod
    def split_id(combined_id):
        if combined_id[:4] == 'feed':
            return (None, combined_id)
        else:
            split = combined_id.split('/', 2)
            return '/'.join(split[:2]), split[-1]

    def sync(self):
        url = utils.api_method('subscription/list')
        msg = auth.message('GET', url)
        utils.session.queue_message(msg, self.on_response, None)

    def on_response(self, session, msg, data=None):
        if 400 <= msg.status_code < 600 or 0 <= msg.status_code < 100:
            logger.error('Subs request returned {0}'.format(msg.status_code))
            return False

        res = json.loads(msg.response_body.data)['subscriptions']
        subs = []
        lbl_id = lambda x: x.split('/', 2)[-1]

        q = 'DELETE FROM subscriptions; DELETE FROM labels;' \
            'DELETE FROM labels_fk'
        utils.sqlite.executescript(q)
        for sub in res:
            # Insert item
            q = 'INSERT INTO subscriptions(id, url, title) VALUES(?, ?, ?)'
            value = (sub['id'], sub['htmlUrl'], sub['title'].strip())
            utils.sqlite.execute(q, value)

            # Add labels
            values = ((lbl_id(l['id']), l['label']) for l in sub['categories'])
            q = 'INSERT OR REPLACE INTO labels(id, name) VALUES(?, ?)'
            utils.sqlite.executemany(q, values)

            # And reestabilish bindings via labels_fk
            values = ((sub['id'], lbl_id(l['id'])) for l in sub['categories'])
            q = 'INSERT INTO labels_fk(item_id, label_id) VALUES(?, ?)'
            utils.sqlite.executemany(q, values)

            if self.favicons.fetch_icon(sub['htmlUrl']):
                self.favicons_syncing += 1

        utils.sqlite.commit()
        self.update()

    def update(self):
        theme = Gtk.IconTheme.get_default()
        flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
        q = '''SELECT subscriptions.id, subscriptions.url, subscriptions.title,
                      labels.id, labels.name
               FROM subscriptions
               LEFT JOIN labels_fk ON labels_fk.item_id = subscriptions.id
               LEFT JOIN labels ON labels.id=labels_fk.label_id'''
        result = set(utils.sqlite.execute(q).fetchall())

        # Add and update labels, will not show labels without subscriptions
        old_labels = dict((item[1], item) for item in self.labels)
        removed_labels = old_labels.copy()
        new_labels = set((item[3], item[4],) for item in result if item[3])
        label_icon = theme.load_icon(Gtk.STOCK_DIRECTORY, 16, flag)
        for label_id, label_title in new_labels:
            if label_id not in old_labels:
                old_labels[label_id] = self[self.append(None)]
            values = {0: SubscriptionType.LABEL, 1: label_id, 2: label_icon,
                      3: label_title}
            self.set(old_labels[label_id].iter, values)
            removed_labels[label_id] = False
        for removed in (row for key, row in removed_labels.items() if row):
            self.remove(removed.iter)

        # Add and update subscriptions
        old_s = dict((item[1], item) for item in self.subscriptions)
        removed_s = old_s.copy()
        for subid, suburl, subtitle, lblid, lbltitle in result:
            label_sub_id = self.combine_ids(lblid, subid)
            if label_sub_id not in old_s:
                iter = old_labels[lblid].iter if lblid in old_labels else None
                old_s[label_sub_id] = self[self.append(iter)]
            values = {0: SubscriptionType.SUBSCRIPTION, 1: label_sub_id,
                      2: utils.icon_pixbuf(suburl), 3: subtitle}
            self.set(old_s[label_sub_id].iter, values)
            removed_s[label_sub_id] = False
        for removed in (row for key, row in removed_s.items() if row):
            self.remove(removed.iter)

        # We've finished
        if self.favicons_syncing == 0:
            self.emit('sync-done')

    def on_icon_update(self, favicons, url):
        self.favicons_syncing -= 1
        current = GLib.get_monotonic_time()
        # Update view at most every quarter a second
        if current - self.last_update > 0.25E6 or self.favicons_syncing == 0:
            self.last_update = current
            self.update()

    def subscribe_to(self, url):
        uri = utils.api_method('subscription/quickadd')
        req_type = 'application/x-www-form-urlencoded'
        data = utils.urlencode({'T': auth.edit_token, 'quickadd': url})
        msg = auth.message('POST', uri)
        msg.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        utils.session.queue_message(msg, self.on_quickadd, None)

    def on_quickadd(self, session, msg, data=None):
        if not 200 <= msg.status_code < 400:
            logger.error('Add request returned {0}'.format(msg.status_code))
            self.emit('subscribed', False)
        res = json.loads(msg.response_body.data)
        self.emit('subscribed', 'streamId' in res)

    def get_item_labels(self, itr):
        row = self[itr]
        if row[0] == SubscriptionType.LABEL:
            return None
        else:
            result = {}
            query = '''SELECT labels_fk.label_id FROM subscriptions
                       LEFT JOIN labels_fk
                       ON labels_fk.item_id = subscriptions.id
                       WHERE subscriptions.id=?'''
            label_id, sub_id = self.split_id(row[1])
            r = utils.sqlite.execute(query, (sub_id,)).fetchall()
            for label in self.labels:
                result[label[1]] = (label[3], label[1] in (i for i, in r))
            return result

    def set_item_label(self, itr, label_id, value):
        if self[itr][0] != SubscriptionType.SUBSCRIPTION:
            logger.error('Adding label to non-subscription!')
            return False

        uri = utils.api_method('subscription/edit')
        req_type = 'application/x-www-form-urlencoded'

        label_id = 'user/-/{0}'.format(label_id)
        action = 'a' if value else 'r'
        item_id = self.split_id(self[itr][1])[1]
        data = utils.urlencode({'T': auth.edit_token, 's': item_id,
                                'ac': 'edit', action: label_id})

        msg = auth.message('POST', uri)
        msg.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        utils.session.queue_message(msg, self.on_sub_edit, None)

    def on_sub_edit(self, session, msg, data=None):
        if not 200 <= msg.status_code < 400:
            logger.error('Edit request returned {0}'.format(msg.status_code))
            return False
        self.sync()


class Favicons(GObject.Object):
    __gsignals__ = {
        'sync-done': (GObject.SignalFlags.RUN_LAST, None, (str,))
    }

    def __init__(self, *args, **kwargs):
        super(Favicons, self).__init__(*args, **kwargs)
        if not os.path.exists(utils.favicon_dir):
            os.makedirs(utils.favicon_dir)

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
