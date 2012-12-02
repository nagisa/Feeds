from gi.repository import Notify, GObject

from trifle import models
from trifle.utils import logger, ngettext, _


class Notification(Notify.Notification):
    icon = GObject.property(type=str, default='trifle')
    visible = GObject.property(type=bool, default=False)
    old_unread = GObject.property(type=int, default=-1)

    def update(self, summary, body):
        super(Notification, self).update(summary, body, self.icon)

    def show(self):
        if models.settings.settings['notifications']:
            self.visible = True
            super(Notification, self).show()
        else:
            logger.warning('Notification was not shown')

    def on_close(self, *args):
        self.visible = False

    def notify_unread_count(self, count):
        if self.old_unread == count and self.visible or count == 0:
            self.old_unread = count # In case count is 0
            # All ok, notification is still visible and displays correct info
            return
        summary = ngettext('Unread item is available', '{0} unread items are '
                           'available', count).format(count)
        self.update(summary, '')
        self.show()
        self.old_unread = count

Notify.init(_('Feeds'))
notification = Notification()
