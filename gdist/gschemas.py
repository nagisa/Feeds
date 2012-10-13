import glob
import os


from distutils.dep_util import newer
from distutils.core import Command
from distutils.spawn import find_executable
from distutils.util import change_root



class build_gschemas(Command):
    """build message catalog files

    Build message catalog (.mo) files from .po files using xgettext
    and intltool.  These are placed directly in the build tree.
    """

    description = "build gschemas used for dconf"
    user_options = []
    build_base = None

    def initialize_options(self):
        pass

    def finalize_options(self):
        self.gschemas_directory = self.distribution.gschemas
        self.set_undefined_options('build', ('build_base', 'build_base'))

    def run(self):
        if find_executable("glib-compile-schemas") is None:
            raise SystemExit("Error: 'glib-compile-schemas' not found.")
        basepath = os.path.join(self.build_base, 'share', 'glib-2.0', 'schemas')
        self.copy_tree(self.gschemas_directory, basepath)


class install_gschemas(Command):
    """install message catalog files

    Copy compiled message catalog files into their installation
    directory, $prefix/share/locale/$lang/LC_MESSAGES/$package.mo.
    """

    description = "install message catalog files"
    user_options = []

    skip_build = None
    build_base = None
    install_base = None
    root = None

    def initialize_options(self):
        pass

    def finalize_options(self):
        self.set_undefined_options('build', ('build_base', 'build_base'))
        self.set_undefined_options(
            'install',
            ('root', 'root'),
            ('install_base', 'install_base'),
            ('skip_build', 'skip_build'))

    def run(self):
        if not self.skip_build:
            self.run_command('build_gschemas')
        src = os.path.join(self.build_base, 'share', 'glib-2.0', 'schemas')
        dest = os.path.join(self.install_base, 'share', 'glib-2.0', 'schemas')
        if self.root != None:
            dest = change_root(self.root, dest)
        self.copy_tree(src, dest)
        self.spawn(['glib-compile-schemas', dest])

__all__ = ["build_gschemas", "install_gschemas"]
