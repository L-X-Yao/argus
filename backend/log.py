"""Structured logging setup."""
import logging
import sys

_fmt = logging.Formatter(
    '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_fmt)

logger = logging.getLogger('gcs')
logger.setLevel(logging.INFO)
logger.addHandler(_handler)
logger.propagate = False
