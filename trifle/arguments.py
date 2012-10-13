from argparse import ArgumentParser


parser = ArgumentParser()
parser.add_argument('--debug', action='store_true',
                    help=_('Show debug messages'))
parser.add_argument('--devtools', action='store_true',
                    help=_('Display WebKit developers tool upon start'))

if 'arguments' not in _globals_cache:
    _globals_cache['arguments'] = parser.parse_args()
arguments = _globals_cache['arguments']
