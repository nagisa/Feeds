# Problem: https://live.gnome.org/GnomeGoals/LibsecretMigration
# But libsecret is not yet available in most repositories.
from gi.repository import GnomeKeyring as GK
from gi.repository import Soup, GObject
from collections import namedtuple

AuthStatus = namedtuple('AuthStatus', 'OK BAD NET_ERROR')(1, 1<<1, 1<<2)

class Auth(GObject.Object):
    __gsignals__ = {
        'status-change': (GObject.SignalFlags.RUN_FIRST, None, []),
        'ask-password': (GObject.SignalFlags.ACTION, None, [])
    }

    def __init__(self, *args, **kwargs):
        super(Auth, self).__init__(*args, **kwargs)
        self.use_keyring = GK.is_available()
        if not self.use_keyring:
            logger.warning('Keyring is not available. Not installed?')
        else:
            self.keyring_name = GK.get_default_keyring_sync()[1]

        self.key = False
        self.status = AuthStatus.OK
        self.soup_session = Soup.SessionAsync()
        # Storage for session, in case keyring is not available
        self.password = None
        self.email = None

    def login(self):
        """
        This method is asynchronous!
        You should connect to 'status-change' signal if you want to receive a
        response upon login (successful or not).
        """
        email, password = self._get_creds()
        if email is None or password is None:
            logger.debug('Cannot login, because didn\'t get email or password')
            return False
        m = Soup.Message.new('POST',
                             'https://www.google.com/accounts/ClientLogin')
        d = 'service=reader&accountType=GOOGLE&Email={email}&Passwd={password}'
        d = d.format(email=email, password=password)
        t = 'application/x-www-form-urlencoded'
        m.set_request(t, Soup.MemoryUse.COPY, d, len(d))
        self.soup_session.queue_message(m, self.logged_in, None)

    def logged_in(self, session, message, data=None):
        logger.debug('Soup status code {0}'.format(message.status_code))
        if 400 <= message.status_code < 500:
            self.status = AuthStatus.BAD
            if not self.key:
                self.emit('ask-password')
        elif message.status_code < 100:
            self.status = AuthStatus.NET_ERROR
        else:
            self.status = AuthStatus.BAD
            for line in message.response_body.data.splitlines():
                if line.startswith('Auth='):
                    self.key = line[5:]
                    self.status = AuthStatus.OK
        self.emit('status-change')

    def _get_creds(self):
        if not self.use_keyring:
            logger.debug('Because keyring is unavailable, giving session vars')
            return self.email, self.password

        attr = GK.Attribute
        attrs = attr.list_new()
        attr.list_append_string(attrs, 'application', 'lightread')
        r = GK.find_items_sync(GK.ItemType.NETWORK_PASSWORD, attrs)
        if r[0] == GK.Result.OK:
            if len(r[1]) > 1:
                logger.debug('More than 1 password belonging to lightread'
                             ' found. Using a first one.')
            result = r[1][0]
            password = result.secret
            email = None
            for attr in GK.Attribute.list_to_glist(result.attributes):
                if attr.name == 'email':
                    email = attr.get_string()
            return email, password
        elif r[0] == GK.Result.NO_MATCH:
            logger.debug('No passwords belonging to lightread found')
        else:
            logger.warning('Unexpected situation occured when retrieving '
                           'a password from keyring')
        return None, None

    def set_creds(self, email, password):
        """
        Returns True if password was saved either for session or in a keyring.
        Will replace a password if one is saved already.
        """
        if not self.use_keyring:
            logger.warning('Password was not saved to keyring, because keyring'
                           ' is not available')
            self.password = password
            self.email = email
        else:
            attr = GK.Attribute
            attrs = attr.list_new()
            attr.list_append_string(attrs, 'email', email)
            attr.list_append_string(attrs, 'application', 'lightread')
            r = GK.item_create_sync(self.keyring_name,
                                GK.ItemType.NETWORK_PASSWORD,
                                'LightRead Password', attrs, password, True)
            return r[0] == GK.Result.OK


if 'auth' not in _globals_cache:
    _globals_cache['auth'] = Auth()
auth = _globals_cache['auth']
