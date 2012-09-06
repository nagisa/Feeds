import os

def get_data_path(*args):
    """ Constructs absolute path to data file """
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data',
                                                                    *args)
    if not os.path.exists(path):
        logger.warning('Constructed path \'{0}\' does not exist'.format(path))
    return path
