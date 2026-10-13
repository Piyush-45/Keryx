import logging

logger = logging.getLogger(__name__)


def main() -> int:
    """Entry point. Stub until the post-call worker is implemented."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Post-call worker starting (stub)")
    return 0
