import logging
import re
import sys
from typing import Any

class SecretMaskingFilter(logging.Filter):
    """
    Ensures that sensitive keys, tokens, and credentials are never written to log outputs.
    """
    SENSITIVE_PATTERNS = [
        re.compile(r'(?i)(api[_-]?key|secret|password|token|bearer|auth|service_role_key)[\s:=]+([^\s,;]+)'),
        re.compile(r'(?i)(AIzaSy[A-Za-z0-9_-]{33})'),
        re.compile(r'(?i)(gsk_[A-Za-z0-9]{32,})'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self.SENSITIVE_PATTERNS:
                record.msg = pattern.sub(r'\1=***REDACTED***', record.msg)
        return True

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Configures application-wide structured logging with secret redaction.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger("weathergpt")
    logger.setLevel(numeric_level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretMaskingFilter())
        logger.addHandler(handler)
        
    return logger

logger = setup_logging()
