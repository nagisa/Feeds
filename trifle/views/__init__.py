from views import application
if 'application' not in _globals_cache:
    _globals_cache['application'] = application.Application()
app = _globals_cache['application']
