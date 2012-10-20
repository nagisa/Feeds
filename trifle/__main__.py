#!/usr/bin/env python
import logging
import trifle
import os

# Create a cache dir if it doesn't exist yet
# Adding this to __init__ will fail us with creating directory belonging to
# root:root while installing, and adding it in application will fail with
# creating this directory too late.
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

from arguments import arguments
# Flags?
if arguments.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug('Logging debug messages')
    logger.debug('Running Py{0}'.format(2 if PY2 else 3))

# Should go latest. Do NOT move this import to the begining
from views import app
app.run(None)
