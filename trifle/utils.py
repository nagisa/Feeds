import os


def get_data_path(*args):
    """ Constructs absolute path to data file """
    path = os.path.join(MODULE_PATH, 'data', *args)
    if not os.path.exists(path):
        logger.warning('Constructed path \'{0}\' does not exist'.format(path))
    return path
