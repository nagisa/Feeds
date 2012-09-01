from datetime import datetime
from gi.repository import GObject, Soup, Gtk
import os
import json


class ItemError(Exception):
    pass


class Items(Gtk.ListStore):

    def __init__(self, *args, **kwargs):
        super(Items, self).__init__(FeedItem, *args, **kwargs)
        self.set_sort_func(0, self.by_date, None)
        self.set_sort_column_id(0, Gtk.SortType.DESCENDING)
        self.added = []
        # populate list from local cache.
        items_dir = os.path.join(CACHE_DIR, self.cache_dir)
        if not os.path.exists(items_dir):
            os.makedirs(items_dir)
        self.load()

    def load(self):
        items_dir = os.path.join(CACHE_DIR, self.cache_dir)
        items = (os.path.join(items_dir, i) for i in os.listdir(items_dir))
        for item in items:
            if os.path.isfile(item) and item not in self.added:
                try:
                    self.append((FeedItem(item),))
                except ItemError as e:
                    logger.warning(e)

    def by_date(self, model, row1, row2, data=None):
        val1 = self.get_value(row1, 0)
        val2 = self.get_value(row2, 0)
        if val1.datetime == val2.datetime:
            return 0
        elif val1.datetime < val2.datetime:
            return -1
        return 1


class AllItems(Items):
    cache_dir = 'all_items'


class FeedItem(GObject.Object):
    def __init__(self, filepath):
        super(FeedItem, self).__init__()
        # Test data
        try:
            with open(filepath) as f:
                data = json.load(f)
        except ValueError as e:
            print(e)
            raise ItemError('Cannot load item {0} due to malformed JSON'
                                                            .format(filepath))
        try:
            self.title = data['title']
            self.site = data['origin']['title']
            self.datetime = datetime.fromtimestamp(data['published'])
            self.icon = None
            self.content = data['content']['content']
            # What to do with this one?!
            self.summary = data['summary']['content']
        except KeyError as e:
            raise ItemError('Cannot load item {0} due to missing data'
                                                            .format(filepath))

        if self.icon is not None and not os.path.exists(self.icon):
            self.icon = None
