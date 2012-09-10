from urllib import parse
from gi.repository import Soup

if 'cacher_session' not in _globals_cache:
    _globals_cache['models_session'] = Soup.SessionAsync(max_conns=50,
                                                         max_conns_per_host=8)
session = _globals_cache['models_session']

class Message(Soup.Message):
    def __new__(cls, *args, **kwargs):
        obj = Soup.Message.new(*args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('User-Agent', 'LightRead/dev')
        return obj

class AuthMessage(Message):
    """
    Creates an Soup.Message object with GoogleLogin headers injected
    """
    def __new__(cls, auth, *args, **kwargs):
        obj = super().__new__(cls, *args, **kwargs)
        hdr = obj.get_property('request-headers')
        hdr.append('Authorization', 'GoogleLogin auth={0}'.format(auth.key))
        return obj

class LoginRequired:
    """Injects ensure_login method which will make sure, that method is
    executed when person is logged in.
    """
    def ensure_login(self, auth, func, *args, **kwargs):
        """
        If auth object has no key, this function will return False, ask
        Auth object to get one and then call func with *args and **kwargs
        """
        if not auth.key:
            logger.debug('auth object has no key, asking to get one')
            def status_change(auth):
                return func(*args, **kwargs)
            auth.login()
            auth.connect('status-change', status_change)
            return False
        return True

def api_method(path, getargs=None):
    if getargs is None:
        getargs = []
    base = 'https://www.google.com/reader/api/0/'
    # Is it dict?
    try:
        getargs = getargs.items()
    except AttributeError:
        pass
    # Will not override earlier output variable
    getargs = getargs + [('output', 'json')]
    return "{0}?{1}".format(parse.urljoin(base, path), parse.urlencode(getargs))
