#!/usr/bin/env python
from argparse import ArgumentParser
import logging

from views import application

# Flags?
parser = ArgumentParser(prog='trifle')
parser.add_argument('--debug', action='store_true',
                    help=_('Show debug messages'))
arguments = parser.parse_args()
if arguments.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug('Logging debug messages')
    logger.debug('Running Py{0}'.format(2 if PY2 else 3))

application = application.Application()
application.run(None)
