from gi.repository import GLib
import os
import sqlite3
import logging

logger = logging.getLogger('trifle')

from trifle.utils import const, get_data_path

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


_sqlite_path = os.path.join(const.CACHE_PATH, 'metadata')
_init_sqlite = not os.path.exists(_sqlite_path)
if _init_sqlite:
    os.makedirs(os.path.dirname(_sqlite_path))
sqlite = SQLite(_sqlite_path)
if _init_sqlite:
    with open(get_data_path('db_init.sql'), 'r') as script:
        sqlite.executescript(script.read())
        sqlite.commit()
