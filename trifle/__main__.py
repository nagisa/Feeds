#!/usr/bin/env python
import logging

import trifle
from views import application
from arguments import arguments

# Flags?
if arguments.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug('Logging debug messages')
    logger.debug('Running Py{0}'.format(2 if PY2 else 3))

application = application.Application()
application.run(None)
