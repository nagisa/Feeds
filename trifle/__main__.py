#!/usr/bin/env python3
from gi.repository import GLib
import logging
import gettext
import os
import signal

from trifle.utils import CACHE_PATH, MODULE_PATH, logger

# Create a cache dir if it doesn't exist yet
# Adding this to __init__ will fail us with creating directory belonging to
# root:root while installing, and adding it in application will fail with
# creating this directory too late.
if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH)

# Logging
class Formatter(logging.Formatter):
    def format(self, record):
        relpath = os.path.relpath(record.pathname, MODULE_PATH)
        record.relpath = relpath
        return super(Formatter, self).format(record)

fmt = "%(levelname)-7s(%(relpath)s:%(lineno)s in %(funcName)s) %(msg)s"
verbose_handler = logging.StreamHandler()
verbose_handler.setFormatter(Formatter(fmt))
fmt = "%(levelname)-7s %(msg)s"
handler = logging.StreamHandler()
handler.setFormatter(Formatter(fmt))

# Set translation domain
localedir = gettext.bindtextdomain('trifle')

# Parse arguments
from trifle.arguments import arguments
logger.addHandler(verbose_handler if arguments.verbose else handler)
logger.setLevel(logging.DEBUG if arguments.debug else logging.WARNING)

# From Transmaggedon
# FIXME: Get rid of the following line which has the only purpose of
# working around Ctrl+C not exiting Gtk applications from bug 622084.
# https://bugzilla.gnome.org/show_bug.cgi?id=622084
# NOTE: Will not execute a cleanup function in application
signal.signal(signal.SIGINT, signal.SIG_DFL)
# Threading support
GLib.threads_init()
# Should go latest. Do NOT move this import to the begining
from trifle.views import application
application.Application().run(None)
