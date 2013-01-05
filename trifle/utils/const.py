from collections import namedtuple
from gi.repository import GLib
import os
import sys

VERSION_INFO = (2, 0, 1)
VERSION = '.'.join(str(part) for part in VERSION_INFO)
# http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
CACHE_PATH = os.path.join(GLib.get_user_cache_dir(), 'trifle')
MODULE_PATH = os.path.dirname(os.path.abspath(sys.argv[0]))
CONTENT_PATH = os.path.join(CACHE_PATH, 'content')
FAVICON_PATH = os.path.join(CACHE_PATH, 'favicons')

SubscriptionType = namedtuple('SubscriptionType', 'LABEL SUBSCRIPTION')(0, 1)

SubscriptionColumn = namedtuple('SubscriptionColumn',
                                'TYPE ID ICON NAME')(*range(4))

ItemsColumn = namedtuple('ItemsColumn', 'ID TITLE SUMMARY LINK TIMESTAMP '\
                         'UNREAD STARRED SUB_URI SUB_TITLE SUB_ID LBL_ID '\
                         'FORCE_VISIBLE')(*range(12))

StateIds = namedtuple('Flags', 'READ KEPT_UNREAD STARRED')(
                               'user/-/state/com.google/read',
                               'user/-/state/com.google/kept-unread',
                               'user/-/state/com.google/starred')
