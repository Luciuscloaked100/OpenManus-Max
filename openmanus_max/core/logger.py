"""
OpenManus-Max Logger
"""

import logging
import sys
from typing import Optional


def get_logger(name: str = "openmanus-max", level: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    return logger


logger = get_logger()
