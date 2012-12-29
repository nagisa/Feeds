from collections import namedtuple
from gi.repository import Soup, Gtk, GdkPixbuf, GLib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlencode, quote, unquote
from xml.sax.saxutils import escape
import hashlib
import itertools
import os
import sqlite3
import ctypes
import json
import re

from trifle.utils import get_data_path, VERSION, CACHE_DIR, logger

# Constants
SubscriptionType = namedtuple('SubscriptionType', 'LABEL SUBSCRIPTION')(0, 1)

ItemsColumn = namedtuple('ItemsColumn', 'ID TITLE SUMMARY LINK TIMESTAMP '\
                         'UNREAD STARRED SUB_URI SUB_TITLE SUB_ID LBL_ID '\
                         'FORCE_VISIBLE')(*range(12))

StateIds = namedtuple('Flags', 'READ KEPT_UNREAD STARRED')(
                               'user/-/state/com.google/read',
                               'user/-/state/com.google/kept-unread',
                               'user/-/state/com.google/starred')


class SQLite(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        self.last_commit_id = None
        self.commit_interval = 2000 #ms
        super(SQLite, self).__init__(*args, **kwargs)

    def commit(self, *args, **kwargs):
        """ Will wait self.commit_interval after last call to commit to
        actually commit everything scheduled.
        Use force_commit to have original behaviour.
        """
        def commit_cb(*args, **kwargs):
            super(SQLite, self).commit(*args, **kwargs)
            logger.debug('Database commit was completed')
            return False

        if self.last_commit_id is not None:
            GLib.source_remove(self.last_commit_id)
        self.last_commit_id = GLib.timeout_add(self.commit_interval, commit_cb)
        return True

    force_commit = sqlite3.Connection.commit


class Message(Soup.Message):
    def __new__(cls, *args, **kwargs):
        obj = Soup.Message.new(*args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('User-Agent', 'Trifle/{0}'.format(VERSION))
        return obj


class AuthMessage(Message):
    """
    Creates an Soup.Message object with GoogleLogin headers injected
    """
    def __new__(cls, auth, *args, **kwargs):
        obj = super(AuthMessage, cls).__new__(cls, *args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('Authorization',
                   'GoogleLogin auth={0}'.format(auth.login_token))
        return obj


class TreeModelFilter(Gtk.TreeModelFilter):
    def set_value(self, iter, column, val):
        # Delegate change to parent
        iter = self.convert_iter_to_child_iter(iter)
        self.get_model().set_value(iter, column, val)


def api_method(path, getargs=None):
    if getargs is None:
        getargs = []
    base = 'https://www.google.com/reader/api/0/'
    # Is it dict?
    try:
        getargs = getargs.items()
    except AttributeError:
        pass
    # Will not override earlier output variable
    getargs = getargs + [('output', 'json')]
    return "{0}?{1}".format(urljoin(base, path), urlencode(getargs))


def icon_name(origin_url):
    value = bytes(origin_url, 'utf-8')
    fname = hashlib.md5(value).hexdigest()
    return os.path.join(CACHE_DIR, 'favicons', fname)


def icon_pixbuf(url):
    """Load cached icon pixbuf from url. Will try to find a suitable fallback
    if nothing found
    """
    fpath = icon_name(url)
    if not os.path.isfile(fpath):
        selections = ['image-loading']
    elif os.path.getsize(fpath) > 10:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(fpath, 16, 16)
    else:
        selections = ['application-rss+xml', 'application-atom+xml',
                      'text-html', Gtk.STOCK_FILE]

    icon_theme = Gtk.IconTheme.get_default()
    icon_flag = Gtk.IconLookupFlags.GENERIC_FALLBACK
    icon = icon_theme.choose_icon(selections, 16, icon_flag)

    if icon is None:
        return None
    else:
        return icon.load_icon()


def split_chunks(itr, chunk_size, fillvalue=None):
    items = [iter(itr)] * chunk_size
    return itertools.zip_longest(*items, fillvalue=fillvalue)


def short_id(item_id):
    if '/' not in item_id:
        # It's probably is not a long id, sorry
        return item_id
    short = ctypes.c_int64(int(item_id.split('/')[-1], 16)).value
    return str(short)


def combine_ids(label_id, sub_id):
    if not label_id:
        return quote(sub_id, '')
    else:
        return quote(label_id, '') + '/' + quote(sub_id, '')


def split_id(combined_ids):
    if not '/' in combined_ids:
        return None, unquote(combined_ids)
    else:
        return tuple(unquote(i) for i in combined_ids.split('/'))


def item_content(item_id):
    fpath = os.path.join(content_dir, str(item_id))
    if os.path.isfile(fpath):
        with open(fpath, 'r') as f:
            return f.read()
    else:
        return None


def process_items(data):

    def process_item(item):
        """
        Should return a (dictionary, content,) pair.
        Dictionary should contain subscription, time, href, author, title and
        summary fields.
        If any of values doesn't exist, they'll be replaced with meaningful
        defaults. For example "Unknown" for author or "Untitled item" for
        title
        """
        # After a lot of fiddling around I realized one thing. We are IN NO
        # WAY guaranteed that any of these fields exists at all.
        # This idiocy should make this method bigger than a manpage for
        # understanding teenage girls' thought processes.
        def strip(text):
            if not text:
                return text
            text = strip.html_re.sub('', text).strip()
            return strip.space_re.sub('', text)
        strip.html_re = re.compile('<.+?>')
        strip.space_re = re.compile('[\t\n\r]+')

        result = {}
        result['subscription'] = item['origin']['streamId']
        result['author'] = item.get('author', None)
        # How could they even think of putting html into feed title?!
        result['title'] = strip(item.get('title', None))

        result['time'] = int(item['timestampUsec'])
        if result['time'] >= int(item.get('updated', -1)) * 1E6:
            result['time'] = item['updated'] * 1E6

        try:
            result['href'] = item['alternate'][0]['href']
        except KeyError:
            result['href'] = item['origin']['htmlUrl']

        content = item['summary']['content'] if 'summary' in item else \
                  item['content']['content'] if 'content' in item else ''
        result['summary'] = strip(content)[:512]

        for k in ['author', 'title', 'summary']:
            result[k] = unescape(result[k]) if result[k] else result[k]

        return result, content

    data = json.loads(data)
    resp = []
    for item in data['items']:
        sid = short_id(item['id'])
        metadata, content = process_item(item)
        # There's no need to replace this one with asynchronous operation as
        # we do everything here in another process anyway.
        fpath = os.path.join(content_dir, str(sid))
        with open(fpath, 'w') as f:
            f.write(content)

        metadata.update({'id': sid})
        resp.append(metadata)
    return resp


unescape = HTMLParser().unescape
session = Soup.SessionAsync(max_conns=50, max_conns_per_host=8)
content_dir = os.path.join(CACHE_DIR, 'content')
favicon_dir = os.path.join(CACHE_DIR, 'favicons')

_sqlite_path = os.path.join(CACHE_DIR, 'metadata')
_init_sqlite = not os.path.exists(_sqlite_path)
sqlite = SQLite(_sqlite_path)
if _init_sqlite:
    with open(get_data_path('db_init.sql'), 'r') as script:
        sqlite.executescript(script.read())
        sqlite.commit()
