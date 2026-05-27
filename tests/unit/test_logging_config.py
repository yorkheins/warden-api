import logging

from warden.infrastructure.logging import configure_logging, get_logger


def test_configure_logging_development():
    configure_logging(log_level="INFO", json_logs=False)
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_production_json():
    configure_logging(log_level="WARNING", json_logs=True)
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_debug():
    configure_logging(log_level="DEBUG", json_logs=False)
    assert logging.getLogger().level == logging.DEBUG


def test_get_logger_returns_bound_logger():
    logger = get_logger("warden.test")
    assert logger is not None
