from gi.repository import Gtk
from gi.repository import GdkPixbuf

from trifle.utils import (SubscriptionType as SubType, sqlite, combine_ids,
                          split_id, icon_pixbuf, SubscriptionColumn as Col)


class Subscriptions(Gtk.TreeStore):

    def __init__(self, *args, **kwargs):
        # SubscriptionType, id for item, icon_fpath, name
        super(Subscriptions, self).__init__(int, str, GdkPixbuf.Pixbuf, str)
        self.set_sort_column_id(Col.NAME, Gtk.SortType.ASCENDING)

    @property
    def labels(self):
        return filter(lambda x: x[Col.TYPE] == SubType.LABEL, self)

    @property
    def subscriptions(self):
        """ Yields all subscriptions in model, including those under
        labels"""
        for item in self:
            if item[Col.TYPE] == SubType.SUBSCRIPTION:
                yield item
            else:
                for sub in item.iterchildren():
                    yield sub

    def update(self):
        theme = Gtk.IconTheme.get_default()
        flag = Gtk.IconLookupFlags.GENERIC_FALLBACK

        q = '''SELECT subscriptions.id, subscriptions.url, subscriptions.title,
                      labels.id, labels.name
               FROM subscriptions
               LEFT JOIN labels_fk ON labels_fk.item_id = subscriptions.id
               LEFT JOIN labels ON labels.id=labels_fk.label_id'''
        result = set(sqlite.execute(q).fetchall())

        label_icon = theme.load_icon(Gtk.STOCK_DIRECTORY, 16, flag)
        labels = {item[3]: item[4] for item in result if item[3] is not None}
        labels_iter = {}
        for row in self.labels:
            # Was it removed?
            if row[Col.ID] not in labels:
                self.remove(row.iter)
                continue;
            # Update it
            row[Col.NAME] = labels.pop(row[Col.ID])
            labels_iter[row[Col.ID]] = row.iter
        # These are not added yet
        for label_id, label_name in labels.items():
            iter = self.append(None)
            labels_iter[label_id] = iter
            self.set(iter, {Col.TYPE: SubType.LABEL, Col.ID: label_id,
                            Col.ICON: label_icon, Col.NAME: label_name})

        subscriptions = {combine_ids(i[3], i[0]): (i[1], i[2]) for i in result}
        for row in self.subscriptions:
            # Was it removed?
            if row[Col.ID] not in subscriptions:
                self.remove(row.iter)
                continue;
            # Update it
            data = subscriptions.pop(row[Col.ID])
            row[Col.NAME], row[Col.ICON] = data[1], icon_pixbuf(data[0])
        # These are not added yet
        for combined_id, d in subscriptions.items():
            iter = self.append(labels_iter.get(split_id(combined_id)[0], None))
            self.set(iter, {Col.ID: combined_id, Col.ICON: icon_pixbuf(d[0]),
                            Col.TYPE: SubType.SUBSCRIPTION, Col.NAME: d[1]})

    def get_item_labels(self, itr):
        row = self[itr]
        if row[0] == SubType.LABEL:
            return None
        else:
            result = {}
            query = '''SELECT labels_fk.label_id FROM subscriptions
                       LEFT JOIN labels_fk
                       ON labels_fk.item_id = subscriptions.id
                       WHERE subscriptions.id=?'''
            label_id, sub_id = split_id(row[1])
            r = sqlite.execute(query, (sub_id,)).fetchall()
            for label in self.labels:
                result[label[1]] = (label[3], label[1] in (i for i, in r))
            return result

