#!/usr/bin/python3
from distutils.core import setup
from distutils.command.build_scripts import build_scripts
from distutils.dep_util import newer
from trifle.utils import VERSION
import gdist
import os


def recursive_include(dir, pre, ext):
    all = []
    old_dir = os.getcwd()
    os.chdir(dir)
    for path, dirs, files in os.walk(pre):
        for file in files:
            if file.split('.')[-1] in ext:
                all.append(os.path.join(path, file))
    os.chdir(old_dir)
    return all


class trifle_build_scripts(build_scripts):
    description = "copy scripts to build directory"

    def run(self):
        self.mkpath(self.build_dir)
        for script in self.scripts:
            newpath = os.path.join(self.build_dir, os.path.basename(script))
            if newpath.lower().endswith(".py"):
                newpath = newpath[:-3]
            if newer(script, newpath) or self.force:
                self.copy_file(script, newpath)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    setup(
        distclass=gdist.GDistribution,
        cmdclass={'build_scripts': trifle_build_scripts},
        name='trifle',
        version=VERSION,
        url='https://github.com/simukis/Feeds',
        description='A lightweight Google Reader for GNOME',
        license='GNU GPL v2',
        packages=['trifle'] + ['trifle.{0}'.format(module) for module in
                               'views models tests'.split()],
        package_data={
            'trifle': recursive_include('trifle', 'data', ('xml', 'svg', 'ui',
                                        'html', 'css', 'sql'))},
        po_directory='po',
        po_package='trifle',
        shortcuts=['trifle.desktop'],
        gschemas='trifle/data/glib-2.0/schemas',
        scripts=['trifle.py'],
        #man_pages=['man/trifle.1']
    )


