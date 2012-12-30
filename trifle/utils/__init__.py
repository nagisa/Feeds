from logging import getLogger

from trifle.utils.const import *
from trifle.utils.common import *
from trifle.utils.overrides import *
from trifle.utils.sqlite import sqlite

logger = getLogger('trifle')
session = Soup.SessionAsync(max_conns=24, max_conns_per_host=8)
