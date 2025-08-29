import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logger():
    """
    Setup and configure the application logger
    """
    logger = logging.getLogger("paperbrain")
    
    # Set default level to INFO, can be overridden later
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # File handler (rotate when file reaches 10MB, keep 5 backup files)
    file_handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=10*1024*1024, 
        backupCount=5
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

# Create logger instance
logger = setup_logger()