import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("app_logger")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.hasHandlers():

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)


    file_handler = RotatingFileHandler(
        "app.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)