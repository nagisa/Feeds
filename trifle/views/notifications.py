from gi.repository import Notify
import functools

from views.utils import connect_once
from models.settings import settings

if not Notify.is_initted():
    Notify.init(_('Feeds'))

class Notification(Notify.Notification):
    icon = 'trifle'
    def __new__(cls, *args, **kw):
        n = Notify.Notification.new('', '', '', *args, **kw)
        n._update, n.update = n.update, functools.partial(cls.update, n)
        n._show, n.show = n.show, functools.partial(cls.show, n)
        n.icon = cls.icon
        n.closed = True
        n.connect('closed', functools.partial(cls.on_close, n))
        return n

    def update(self, summary, body):
        self._update(summary, body, self.icon)

    def show(self):
        if settings['notifications']:
            self.closed = False
            self._show()
        else:
            logger.warning('Notification was not shown')

    def on_close(self, *args):
        self.closed = True

if 'notification' not in _globals_cache:
    _globals_cache['notification'] = Notification()
notification = _globals_cache['notification']
