from concurrent import futures
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from threading import Thread, Lock
"""
A module for easy combination of MainLoop and off-MainThread processing.

Usage example:

    exe = JobExecutor()
    exe.start()
    job = exe.submit(fn, *args, **kwargs) # Submit your jobs

    def callback(job, success):
        success # Boolean indicating if job succeeded. If it's false, expect
                # exception.
        job.result()
        exe.stop()

    job.connect('finished', callback) # Get notified when a job is complete

Don't forget to call `GLib.threads_init()`
"""


class Job(GObject.Object):
    __gsignals__ = {
        'finished': (GObject.SignalFlags.RUN_LAST, None, [bool])
    }
    future = GObject.property(type=object)

    def __init__(self, fn, args, kw, **kwargs):
        self._fn, self._args, self._kw = fn, args, kw
        super(Job, self).__init__(**kwargs)

    def execute(self, executor):
        self.future = executor.submit(self._fn, *self._args, **self._kw)
        self.future.add_done_callback(self.on_done)

    def on_done(self, future):
        def emit_signals(job, future):
            job.emit('finished', future.exception() is None)
        GLib.idle_add(emit_signals, self, future)

    def result(self):
        """ Result of computation """
        return self.future.result()

    def exception(self):
        return self.future.exception()


class JobExecutor(Thread):
    def __init__(self):
        super(JobExecutor, self).__init__(daemon=True)
        self._submissions = []
        self._lock = Lock()
        self._should_stop = False
        self.running = False

    def run(self):
        running = True
        self._executor = executor = futures.ProcessPoolExecutor()
        while True:
            while self._submissions:
                job = self._submissions.pop()
                job.execute(executor)

            self._lock.acquire()
            if self._should_stop:
                break

        self._executor.shutdown(wait=True)
        GLib.idle_add(self.join)

    def submit(self, fn, *args, **kwargs):
        """ Will submit a job for processing. It doesn't matter if you submit
        your jobs before calling .start() or after.
        """
        job = Job(fn, args, kwargs)
        self._submissions.append(job)
        self.do_iter()
        return job

    def do_iter(self):
        try:
            self._lock.release()
        except RuntimeError:
            pass

    def stop(self):
        """ Notifies worker it should stop. Worker will stop only when it
        completes (cancellation is completion as well) all schedulled work.
        """
        self._should_stop = True
        self.do_iter()
