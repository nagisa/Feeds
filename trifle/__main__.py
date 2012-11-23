#!/usr/bin/env python3
import logging
import os

import trifle
from trifle.utils import CACHE_DIR, logger

# Create a cache dir if it doesn't exist yet
# Adding this to __init__ will fail us with creating directory belonging to
# root:root while installing, and adding it in application will fail with
# creating this directory too late.
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

from arguments import arguments
if arguments.debug:
    logger.setLevel(logging.DEBUG)

# Should go latest. Do NOT move this import to the begining
from views import application
application.Application().run(None)
