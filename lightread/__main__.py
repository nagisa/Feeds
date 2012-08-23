#!/usr/bin/env python

from lightread.views import application
from argparse import ArgumentParser
import logging

# Flags?
parser = ArgumentParser(prog='lightread')
parser.add_argument('--debug', action='store_true',
                    help=_('Show debug messages'))
arguments = parser.parse_args()
if arguments.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug('Logging debug messages')
    logger.debug('Lightread running Py{0}'.format(2 if PY2 else 3))

# At last – run lightread
lightread = application.Application()
lightread.run(None)
