# -*- encoding: utf-8 -*-
# Problem: https://live.gnome.org/GnomeGoals/LibsecretMigration
# But libsecret doesn't have introspection yet.

from collections import defaultdict
from gi.repository import GObject
from gi.repository import Soup
from gi.repository import GLib

from trifle.models import utils
from trifle.utils import logger

class Auth(GObject.Object):
    status = GObject.property(type=object)
    login_token = GObject.property(type=str)
    edit_token = GObject.property(type=str)
    edit_token_expire = GObject.property(type=GObject.TYPE_UINT64)

    def __init__(self, *args, **kwargs):
        super(Auth, self).__init__(*args, **kwargs)
        self.login_callbacks = []
        self.edit_token_expire = 0
        self.status = defaultdict(bool)

    def message(self, *args, **kwargs):
        return utils.AuthMessage(self, *args, **kwargs)

    def login(self, callback):
        self.login_callbacks.append(callback)
        if self.status['PROGRESS']:
            logger.error('Already logging in')
        else:
            self.status.update({'PROGRESS': True, 'ABORTED': False,
                                'BAD_CREDENTIALS': False, 'OK': False})
            keyring.load_credentials(self.on_credentials)

    def on_credentials(self):
        if not keyring.has_credentials:
            self.status.update({'ABORTED': True, 'PROGRESS': False})
            logger.debug('callback without credentials, assuming abort')
            utils.run_callbacks(self.login_callbacks)
            return

        uri = 'https://www.google.com/accounts/ClientLogin'
        data = 'service=reader&accountType=GOOGLE&Email={0}&Passwd={1}'
        data = data.format(keyring.username, keyring.password)
        message = utils.Message('POST', uri)
        req_type = 'application/x-www-form-urlencoded'
        message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        utils.session.queue_message(message, self.on_login, None)

    def on_login(self, session, message, data):
        status = message.status_code
        if not 200 <= status < 400:
            logger.error('Authentication failed (HTTP {0})'.format(status))
            self.status.update({'OK': False, 'PROGRESS': False,
                                'BAD_CREDENTIALS': status == 403})
            utils.run_callbacks(self.login_callbacks)
        else: # Login was likely successful
            for line in message.response_body.data.splitlines():
                if line.startswith('Auth'):
                    self.login_token = line[5:]
                    message = self.message('GET', utils.api_method('token'))
                    utils.session.queue_message(message, self.on_token, None)
                    break

    def on_token(self, session, message, data=None):
        status = message.status_code
        if not 200 <= status < 400:
            logger.error('Token request failed (HTTP {0})'.format(status))
            self.status['OK'] = False
        else:
            self.edit_token = message.response_body.data
            self.edit_token_expire = int(GLib.get_real_time() + 1.5E9) #µs
            self.status['OK'] = True
        self.status['PROGRESS'] = False
        utils.run_callbacks(self.login_callbacks)

    def token_valid(self):
        return GLib.get_real_time() < self.edit_token_expire


class Keyring(GObject.Object):
    __gsignals__ = {
        'ask-password': (GObject.SignalFlags.ACTION, None, [object])
    }
    username = GObject.property(type=str)
    password = GObject.property(type=str)

    def __init__(self, *args, **kwargs):
        super(Keyring, self).__init__(*args, **kwargs)
        self.load_callbacks = []

    @property
    def has_credentials(self):
        return self.username and self.password

    def load_credentials(self, callback):
        if self.has_credentials:
            callback()
        else:
            self.load_callbacks.append(callback)
            resp_callback = lambda: utils.run_callbacks(self.load_callbacks)
            self.emit('ask-password', resp_callback)

    def set_credentials(self, username, password):
        self.username, self.password = username, password
        return True

    def invalidate_credentials(self):
        self.username, self.password = None, None


class GKeyring(Keyring):
    @property
    def keyring(self):
        if GnomeKeyring.is_available():
            return GnomeKeyring.get_default_keyring_sync()[1]
        return None

    def load_credentials(self, callback):
        keyring = self.keyring
        if self.has_credentials:
            callback()
        elif keyring is None:
            # We degrade to a simple session keyring
            return super(GKeyring, self).load_credentials(callback)
        else:
            self.load_callbacks.append(callback)
            Attribute = GnomeKeyring.Attribute
            queryset = Attribute.list_new()
            Attribute.list_append_string(queryset, 'application', 'trifle')
            itemtype = GnomeKeyring.ItemType.NETWORK_PASSWORD
            status, result = GnomeKeyring.find_items_sync(itemtype, queryset)
            if len(result) > 1:
                logger.warning('More than one trifle passwords found')

            if status == GnomeKeyring.Result.OK:
                self.password = result[0].secret
                for attribute in Attribute.list_to_glist(result[0].attributes):
                    if attribute.name == 'user':
                        self.username = attribute.get_string()
                utils.run_callbacks(self.load_callbacks)
            else:
                # We again degrade to simple session keyring
                cback = lambda: utils.run_callbacks(self.load_callbacks)
                return super(GKeyring, self).load_credentials(cback)

    def set_credentials(self, username, password):
        Attribute = GnomeKeyring.Attribute
        attributes = Attribute.list_new()
        Attribute.list_append_string(attributes, 'application', 'trifle')
        Attribute.list_append_string(attributes, 'user', username)
        itemtype = GnomeKeyring.ItemType.NETWORK_PASSWORD
        status, _ = GnomeKeyring.item_create_sync(self.keyring,
                                                  itemtype,
                                                  'Trifle Password',
                                                  attributes, password, True)

        return super(GKeyring, self).set_credentials(username, password) or \
               status == GnomeKeyring.Result.OK

    def invalidate_credentials(self):
        Attribute = GnomeKeyring.Attribute
        queryset = Attribute.list_new()
        Attribute.list_append_string(queryset, 'application', 'trifle')
        itemtype = GnomeKeyring.ItemType.NETWORK_PASSWORD
        status, results = GnomeKeyring.find_items_sync(itemtype, queryset)
        for result in results:
            GnomeKeyring.item_delete_sync(result.keyring, result.item_id)
        super(GKeyring, self).invalidate_credentials()


try:
    from gi.repository import GnomeKeyring
    keyring = GKeyring()
except ImportError:
    keyring = Keyring()
auth = Auth()
