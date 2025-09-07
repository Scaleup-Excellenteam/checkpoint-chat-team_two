import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Responsible for setting up logging for the application

def setup_logging():
    # make sure logs dir exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # create loggers
    app_logger = logging.getLogger("app")
    sec_logger = logging.getLogger("security")
    app_logger.setLevel(logging.INFO)
    sec_logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    # rotating file handlers + console for app
    app_fh = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3)
    app_fh.setFormatter(fmt)
    app_logger.addHandler(app_fh)

    sec_fh = RotatingFileHandler(log_dir / "security.log", maxBytes=1_000_000, backupCount=3)
    sec_fh.setFormatter(fmt)
    sec_logger.addHandler(sec_fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    app_logger.addHandler(ch)

    return app_logger, sec_logger