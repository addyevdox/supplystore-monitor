import logging


def make(*, name, filename=None):
    screen_logger = logging.getLogger('screen_logger')
    screen_logger.setLevel(logging.INFO)

    streamFormatter = logging.StreamHandler()

    streamFormatter.setFormatter(logging.Formatter('%(asctime)s %(message)s'))

    if filename is not None:
        fileFormatter = logging.FileHandler(filename)
        fileFormatter.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        screen_logger.addHandler(fileFormatter)

    screen_logger.addHandler(streamFormatter)

    return screen_logger
