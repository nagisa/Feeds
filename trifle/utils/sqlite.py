from gi.repository import GLib, GObject
import os
import sqlite3
import logging
import threading
import queue

logger = logging.getLogger('trifle')

from trifle.utils import const, async, get_data_path


class SQLite(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(SQLite, self).__init__(daemon=True)
        # Contains jobs in form of (SQLiteJob, callable, args, kwargs)
        self._jobs = queue.Queue()
        self._args, self._kwargs = args, kwargs

    def run(self):
        with sqlite3.Connection(*self._args, **self._kwargs) as cnn:
            del self._args, self._kwargs
            while True:
                job, method, args, kwargs = self._jobs.get()
                if method is None:
                    break
                try:
                    result = getattr(cnn, method)(*args, **kwargs)
                    if hasattr(result, 'fetchall'):
                        job.result = result.fetchall()
                    else:
                        job.result = result
                    GLib.idle_add(job.emit, 'finished', True)
                except: # Yes, catch 'em all!
                    logger.exception('SQLite error')
                    GLib.idle_add(job.emit, 'finished', False)
                self._jobs.task_done()
        GLib.idle_add(self.join)

    def commit(self, *args, **kwargs):
        job = async.Job()
        self._jobs.put((job, 'commit', args, kwargs))
        return job

    def execute(self, *args, **kwargs):
        job = async.Job()
        self._jobs.put((job, 'execute', args, kwargs))
        return job

    def executemany(self, *args, **kwargs):
        job = async.Job()
        self._jobs.put((job, 'executemany', args, kwargs))
        return job

    def executescript(self, *args, **kwargs):
        job = async.Job()
        self._jobs.put((job, 'executescript', args, kwargs))
        return job

    def stop(self, *args, **kwargs):
        self._jobs.put((None, None, None, None,))


_sqlite_path = os.path.join(const.CACHE_PATH, 'metadata')
_init_sqlite = not os.path.exists(_sqlite_path)
if _init_sqlite and not os.path.exists(os.path.dirname(_sqlite_path)):
    os.makedirs(os.path.dirname(_sqlite_path))

# Started in views.application.Application.on_startup
sqlite = SQLite(_sqlite_path)

if _init_sqlite:
    with open(get_data_path('db_init.sql'), 'r') as script:
        sqlite.executescript(script.read())
        sqlite.commit()
