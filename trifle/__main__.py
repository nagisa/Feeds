#!/usr/bin/env python3
import logging
import os
import signal

from trifle.utils import CACHE_DIR, logger, verbose_handler, handler

# Create a cache dir if it doesn't exist yet
# Adding this to __init__ will fail us with creating directory belonging to
# root:root while installing, and adding it in application will fail with
# creating this directory too late.
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

from trifle.arguments import arguments
logger.addHandler(verbose_handler if arguments.verbose else handler)
logger.setLevel(logging.DEBUG if arguments.debug else logging.WARNING)


# From Transmaggedon
# FIXME: Get rid of the following line which has the only purpose of
# working around Ctrl+C not exiting Gtk applications from bug 622084.
# https://bugzilla.gnome.org/show_bug.cgi?id=622084
# NOTE: Will not execute a cleanup function in application
signal.signal(signal.SIGINT, signal.SIG_DFL)


# Should go latest. Do NOT move this import to the begining
from trifle.views import application
application.Application().run(None)
