from gi.repository import Notify, GObject

from trifle.models import settings
from trifle.utils import logger, ngettext, _


class Notification(Notify.Notification):
    icon = GObject.property(type=str, default='trifle')
    visible = GObject.property(type=bool, default=False)
    old_unread = GObject.property(type=int, default=-1)

    def update(self, summary, body):
        super(Notification, self).update(summary, body, self.icon)

    def show(self):
        if settings['notifications']:
            self.visible = True
            super(Notification, self).show()
        else:
            logger.warning('Notification was not shown')

    def on_close(self, *args):
        self.visible = False

    def notify_unread_count(self, count):
        if self.old_unread == count and self.visible:
            # All ok, notification is still visible and displays correct info
            return
        summary = ngettext('You have an unread item',
                           'You have {0} unread items', count).format(count)
        self.update(summary, '')
        self.show()


Notify.init(_('Feeds'))
notification = Notification()
