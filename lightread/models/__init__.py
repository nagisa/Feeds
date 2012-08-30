from datetime import datetime
from gi.repository import GObject
import os

from lightread.models.settings import settings

class FeedItem(GObject.Object):
    def __init__(self):
        super(FeedItem, self).__init__()
        # Test data
        self.title = 'Test'
        self.site = 'The Blog!'
        self.datetime = datetime.now().replace(second=0)#'2012-08-30T11:24:53Z'
        self.icon = '/home/nagisa/.cache/lightread/feed-1/favicon.png'
        self.content = 'Last day I did that, then I did this, but after that ' \
                       'another thing was done. At last I did that but then ' \
                       'I did nothing.'

        if not os.path.exists(self.icon):
            self.icon = None
