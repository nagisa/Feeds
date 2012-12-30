from argparse import ArgumentParser
from gettext import gettext as _

parser = ArgumentParser()
parser.add_argument('-d', '--debug', action='store_true',
                    help=_('Show debug messages'))
parser.add_argument('-v', '--verbose', action='store_true',
                    help=_('More verbose messages'))
parser.add_argument('--devtools', action='store_true',
                    help=_('Display WebKit developers tool upon start'))

arguments = parser.parse_args()
