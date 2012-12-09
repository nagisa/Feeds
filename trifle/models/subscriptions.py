from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import Soup

from trifle.models import utils
from trifle.models.utils import SubscriptionType
from trifle.utils import logger


class Subscriptions(Gtk.TreeStore):

    def __init__(self, *args, **kwargs):
        # SubscriptionType, id for item, icon_fpath, name
        super(Subscriptions, self).__init__(int, str, GdkPixbuf.Pixbuf, str)
        self.set_sort_column_id(3, Gtk.SortType.ASCENDING)

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
            label_sub_id = utils.combine_ids(lblid, subid)
            if label_sub_id not in old_s:
                iter = old_labels[lblid].iter if lblid in old_labels else None
                old_s[label_sub_id] = self[self.append(iter)]
            values = {0: SubscriptionType.SUBSCRIPTION, 1: label_sub_id,
                      2: utils.icon_pixbuf(suburl), 3: subtitle}
            self.set(old_s[label_sub_id].iter, values)
            removed_s[label_sub_id] = False
        for removed in (row for key, row in removed_s.items() if row):
            self.remove(removed.iter)

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
            label_id, sub_id = utils.split_id(row[1])
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
        item_id = utils.split_id(self[itr][1])[1]
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
