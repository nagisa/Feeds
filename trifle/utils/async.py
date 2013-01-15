from concurrent import futures
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from threading import Thread, Lock, current_thread
from queue import Queue
"""
A module for easy combination of MainLoop and off-MainThread processing.

Usage example:

    exe = JobExecutor()
    exe.start()
    job = exe.submit(fn, *args, **kwargs) # Submit your jobs

    def callback(job, success):
        success # Boolean indicating if job succeeded. If it's false, expect
                # exception.
        job.result
        exe.stop()

    job.connect('finished', callback) # Get notified when a job is complete

Don't forget to call `GLib.threads_init()`
"""


class Job(GObject.Object):
    __gsignals__ = {
        'finished': (GObject.SignalFlags.RUN_LAST, None, [bool])
    }
    result = GObject.property(type=object, default=None)


class ExecutorJob(Job):
    future = GObject.property(type=object)

    def __init__(self, *args, **kwargs):
        super(ExecutorJob, self).__init__(*args, **kwargs)

        def bind(s, p):
            cb = lambda x: GLib.idle_add(self.finished)
            self.future.add_done_callback(cb)
        self.connect('notify::future', bind)

    @GObject.property
    def result(self):
        return self.future.result()

    @GObject.property
    def exception(self):
        return self.future.exception()

    def finished(self):
        self.emit('finished', self.exception is None)


class JobExecutor(Thread):
    def __init__(self):
        super(JobExecutor, self).__init__(daemon=True)
        # Contains items in form of (Job, fn, args, kwargs)
        # if second argument is None, it indicates thread should finish by
        # reaching that specific element
        self._jobs = Queue()

    def run(self):
        executor = futures.ProcessPoolExecutor()
        while True:
            job, fn, args, kwargs = self._jobs.get()
            if fn is None:
                break
            job.future = executor.submit(fn, *args, **kwargs)

        executor.shutdown(wait=True)
        GLib.idle_add(self.join)

    def submit(self, fn, *args, **kwargs):
        """ Will submit a job for processing. It doesn't matter if you submit
        your jobs before calling .start() or after.
        """
        job = ExecutorJob()
        self._jobs.put((job, fn, args, kwargs,))
        return job

    def stop(self):
        """ Notifies worker it should stop. Worker will stop only when it
        completes (cancellation is completion as well) all work schedulled
        before call of this function.
        """
        self._jobs.put((None, None, None, None,))
