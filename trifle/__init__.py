import signal
import sys

from trifle.utils import MODULE_PATH
sys.path.insert(0, MODULE_PATH)

# From Transmaggedon
# FIXME: Get rid of the following line which has the only purpose of
# working around Ctrl+C not exiting Gtk applications from bug 622084.
# https://bugzilla.gnome.org/show_bug.cgi?id=622084
# NOTE: Will not execute a cleanup
signal.signal(signal.SIGINT, signal.SIG_DFL)
