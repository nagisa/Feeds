from distutils.core import setup, Command
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

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    setup(
        distclass=gdist.GDistribution,
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
        gschemas='trifle/data/glib-2.0/schemas'
        #man_pages=['man/trifle.1']
    )


