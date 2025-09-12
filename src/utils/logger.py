import logging
import sys
from datetime import datetime
from pathlib import Path
from config.settings import LOGS_DIR, AppConfig

def setup_logger(name: str, log_file: str = None, level: str = None) -> logging.Logger:
    if level is None:
        level = AppConfig.LOG_LEVEL
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    # Set encoding to utf-8 for Unicode support
    if hasattr(console_handler.stream, 'reconfigure'):
        console_handler.stream.reconfigure(encoding='utf-8')
    logger.addHandler(console_handler)
    
    if log_file is None:
        log_file = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
    
    file_handler = logging.FileHandler(LOGS_DIR / log_file, encoding='utf-8')
    file_handler.setLevel(getattr(logging, level.upper()))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)