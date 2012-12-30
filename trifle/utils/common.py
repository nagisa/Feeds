from gettext import gettext as _, ngettext
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango
from logging import getLogger
from urllib.parse import urljoin, urlencode, quote, unquote
import ctypes
import hashlib
import itertools
import os

from trifle.utils import const

logger = getLogger('trifle')


def hexcolor(color):
    """ Takes GdkColor and returns string represantation suitable for use
    in Pango, CSS and HTML """
    args = (color.red * 0xFF, color.green * 0xFF, color.blue * 0xFF)
    return '#{0:02.0X}{1:02.0X}{2:02.0X}'.format(*(int(a) for a in args))


def parse_font(string):
    """ Parses font into font-family and font-size """
    font = Pango.font_description_from_string(string)
    if font is None:
        return (None, None)
    return (font.get_family(), font.get_size() / Pango.SCALE)


def time_ago(timestamp):
    """
    String representation of how long ago timestamp is from current date
    """
    seconds = GLib.get_real_time() / 1E6 - timestamp
    if seconds < 0:
        logger.warning('Timestamp in the future')
        return _('From the future')
    elif seconds < 60:
        return _('Just now')
    elif seconds < 3600:
        minutes = int(seconds / 60)
        min_fmt = ngettext('{0} minute ago', '{0} minutes ago', minutes)
        return min_fmt.format(minutes)
    elif seconds < 86400:
        hours = int(seconds / 3600)
        hour_fmt = ngettext('{0} hour ago', '{0} hours ago', hours)
        return hour_fmt.format(hours)
    else:
        days = int(seconds / 86400)
        day_fmt = ngettext('{0} day ago', '{0} days ago', days)
        return day_fmt.format(days)


def connect_once(obj, signal, callback, data=None):
    """ Connects to a signal and disconnects from it on the first emision of
    signal """
    def disconnect_and_callback(callback):
        def handler(*args, **kwargs):
            obj.disconnect(cnn_id)
            callback(*args, **kwargs)
        return handler
    cnn_id = obj.connect(signal, disconnect_and_callback(callback), data)


def get_data_path(*args):
    """ Constructs absolute path to data file """
    path = os.path.join(const.MODULE_PATH, 'data', *args)
    if not os.path.exists(path):
        logger.warning('Constructed path \'{0}\' does not exist'.format(path))
    return path


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


def icon_name(origin_url):
    value = bytes(origin_url, 'utf-8')
    fname = hashlib.md5(value).hexdigest()
    return os.path.join(const.FAVICON_PATH, fname)


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
