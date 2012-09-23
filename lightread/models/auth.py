# Problem: https://live.gnome.org/GnomeGoals/LibsecretMigration
# But libsecret is not yet available in most repositories.
from gi.repository import GnomeKeyring as GK
from gi.repository import Soup, GObject, GLib
import json

from lightread.models import utils
AuthStatus = utils.AuthStatus

class Auth(GObject.Object):
    __gsignals__ = {
        'status-change': (GObject.SignalFlags.RUN_FIRST, None, []),
        'token-available': (GObject.SignalFlags.RUN_FIRST, None, []),
    }

    def __init__(self, *args, **kwargs):
        super(Auth, self).__init__(*args, **kwargs)
        self.secrets = SecretStore()
        # These variables must filled after login
        self.key = None
        self.info = None
        self._token = None
        self.token_expires = -1
        self.status = AuthStatus.BAD

        self._url = 'https://www.google.com/accounts/ClientLogin'
        self._data = 'service=reader&accountType=GOOGLE&Email={0}&Passwd={1}'

    def login(self):
        """
        This method is asynchronous!
        You should connect to 'status-change' signal if you want to receive a
        response upon login (successful or not).
        """
        if self.status == AuthStatus.PROGRESS:
            logger.debug('Already authentificating')
            return False
        self.status = AuthStatus.PROGRESS

        self.key = None
        user, password = self.secrets['user'], self.secrets['password']
        if user is None or password is None:
            logger.debug('Cannot login, because didn\'t get email or password')
            return False

        message = utils.Message('POST', self._url)
        req_type = 'application/x-www-form-urlencoded'
        data = self._data.format(user, password)
        message.set_request(req_type, Soup.MemoryUse.COPY, data, len(data))
        utils.session.queue_message(message, self.on_login, None)

    @property
    def token(self):
        current_time = GLib.get_monotonic_time()
        if current_time > self.token_expires:
            message = utils.AuthMessage(self, 'GET', utils.api_method('token'))
            utils.session.queue_message(message, self.on_token, None)
            return False
        else:
            return self._token

    def on_login(self, session, message, data=None):
        """
        Should set state of Auth object to show state of login and key
        """
        if 400 <= message.status_code < 500:
            logger.debug('Auth failed with {0}'.format(message.status_code))
            self.status = AuthStatus.BAD
        elif message.status_code < 100 or 500 <= message.status_code < 600:
            logger.debug('Auth failed with {0}'.format(message.status_code))
            self.status = AuthStatus.NET_ERROR
        else:
            self.status = AuthStatus.BAD
            for line in message.response_body.data.splitlines():
                if line.startswith('Auth='):
                    # Set state of login
                    self.key = line[5:]
                    self.status = AuthStatus.OK

        if self.status == AuthStatus.OK:
            # Try to get user information
            message = utils.AuthMessage(self, 'GET',
                                        utils.api_method('user-info'))
            utils.session.queue_message(message, self.on_user_data, None)
        elif self.status == AuthStatus.BAD:
            self.secrets.emit('ask-password')

    def on_user_data(self, session, message, data=None):
        info = json.loads(message.response_body.data)
        self.info = {'id': info['userId']}
        self.emit('status-change')

    def on_token(self, session, message, data=None):
        if 400 <= message.status_code < 500:
            logger.debug('Token failed with {0}'.format(message.status_code))
        elif message.status_code < 100 or 500 <= message.status_code < 600:
            logger.debug('Token failed with {0}'.format(message.status_code))
        else:
            self._token = message.response_body.data
            self.token_expires = GLib.get_monotonic_time() + 1.5E9 #µs = 25min
            self.emit('token-available')


class SecretStore(GObject.Object):
    __gsignals__ = {
        'ask-password': (GObject.SignalFlags.ACTION, None, [])
    }
    keys = ('user', 'password',)

    def __init__(self, *args, **kwargs):
        super(SecretStore, self).__init__(*args, **kwargs)

        self._password, self._user = None, None
        self._use_keyring = GK.is_available()
        if not self._use_keyring:
            logger.warning('Keyring is not available')
        else:
            self._keyring_name = GK.get_default_keyring_sync()[1]

    def _load_creds(self):
        if not self._use_keyring:
            logger.debug('Because keyring is unavailable, loaded nothing')
            raise EnvironmentError('Could not load password')

        queryset = GK.Attribute.list_new()
        GK.Attribute.list_append_string(queryset, 'application', 'lightread')
        status, result = GK.find_items_sync(GK.ItemType.NETWORK_PASSWORD,
                                            queryset)
        if len(result) > 1:
            logger.warning('>1 lightread specific secrets found')

        if status == GK.Result.OK:
            self._password = result[0].secret
            for attribute in GK.Attribute.list_to_glist(result[0].attributes):
                if attribute.name == 'user':
                    self._user = attribute.get_string()
            return True # All OK!
        elif status == GK.Result.NO_MATCH:
            logger.debug('No lightread specific secrets found')
        else:
            logger.warning('Unexpected keyring error occured')
        raise EnvironmentError('Could not load password')

    def __getitem__(self, key):
        if self._password is None and self._user is None:
            try:
                self._load_creds()
            except EnvironmentError:
                self.emit('ask-password')
                return None

        if key in self.keys:
            value = getattr(self, '_{0}'.format(key))
            if value is None:
                logger.debug('Getting {0} before setting it'.format(key))
            return value
        raise KeyError('There\'s no key named {0}'.format(key))

    def set(self, user, password):
        self._user, self._password = user, password

        if not self._use_keyring:
            logger.warning('Keyring is unavailable, didn\'t save the secret')
            return False

        attributes = GK.Attribute.list_new()
        GK.Attribute.list_append_string(attributes, 'application', 'lightread')
        GK.Attribute.list_append_string(attributes, 'user', user)
        status, _ = GK.item_create_sync(self._keyring_name,
                                        GK.ItemType.NETWORK_PASSWORD,
                                        'LightRead Password',
                                        attributes, password, True)
        return status == GK.Result.OK


if 'auth' not in _globals_cache:
    _globals_cache['auth'] = Auth()
auth = _globals_cache['auth']
