# Blockchain/Backend/util/logging_config.py

import logging
import logging.handlers
import os
import sys
import re
from pathlib import Path

# --- Configuration (Keep as before) ---
DEFAULT_LOG_LEVEL = logging.INFO
DEBUG_LOG_LEVEL = logging.DEBUG
LOG_FORMAT = '%(asctime)s %(levelname)-8s [PID:%(process)d][%(name)-12s]: %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# --- Node ID Detection (Keep as before) ---
def get_node_id_from_cwd():
    # ... (implementation from previous answer) ...
    cwd = os.getcwd()
    if "validator_node" in cwd: return "validator"
    match = re.search(r'node_(\d+)', cwd)
    if match: return int(match.group(1))
    print("WARNING [logging_config]: Could not determine node ID from CWD.", file=sys.stderr)
    return None

# --- Class to Redirect stdout/stderr to Logger ---
class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            # Log messages line by line
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        # Required for file-like object interface
        pass

    def isatty(self):
        # Pretend it's not a TTY to maybe avoid certain formatting issues
        return False

# --- Logging Setup Function (Modified) ---
_logging_configured = False

def setup_node_logging(node_id=None, log_level=DEFAULT_LOG_LEVEL, log_to_console=False, redirect_std_streams=True): # Added redirect flag
    """
    Configures logging handlers for a specific node.
    Optionally redirects stdout and stderr to the logging system.
    """
    global _logging_configured
    # Prevent re-configuration *within the same process*
    # Checking process ID might be needed if using fork without exec
    if _logging_configured and getattr(logging, '_process_id', None) == os.getpid():
        return

    if node_id is None: node_id = get_node_id_from_cwd()

    # Determine log directory (keep path logic as before)
    log_base_dir = None
    try:
        util_dir = Path(__file__).parent.resolve(); backend_dir = util_dir.parent
        blockchain_dir = backend_dir.parent; code_node_dir = blockchain_dir.parent
        project_root_dir = code_node_dir.parent
        node_dir_name = f"node_{node_id}" if isinstance(node_id, int) else "validator_node"
        if node_id is None: node_dir_name = "unknown_node" # Handle None case
        log_base_dir = project_root_dir / "network_data" / node_dir_name / "logs"
        log_base_dir.mkdir(parents=True, exist_ok=True)
        main_log_file = log_base_dir / f"node_{node_id}.log"
    except Exception as e:
        print(f"ERROR [logging_config]: Failed to determine log paths: {e}", file=sys.stderr)
        # Fallback to basic console if paths fail
        logging.basicConfig(level=log_level, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, stream=sys.stderr)
        logging._process_id = os.getpid() # Mark process ID
        _logging_configured = True
        return

    # --- Configure Root Logger ---
    root_logger = logging.getLogger()
    # Remove existing handlers added by previous calls or basicConfig
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(DEBUG_LOG_LEVEL) # Capture all levels at root

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # --- Setup Handlers ---
    # Rotating File Handler (catches all logs at or above log_level)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            main_log_file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level) # File handler minimum level
        root_logger.addHandler(file_handler)
    except Exception as e:
         print(f"ERROR [logging_config]: Failed to create file handler {main_log_file}: {e}", file=sys.stderr)
         log_to_console = True # Force console if file fails

    # Console Handler (optional)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level) # Console handler minimum level
        root_logger.addHandler(console_handler)

    # --- Redirect stdout/stderr (Optional) ---
    if redirect_std_streams:
        print(f"INFO [LoggingConfig]: Redirecting stdout/stderr for PID {os.getpid()} to logs.", file=sys.stderr) # Print before redirect
        # Redirect stdout to log at INFO level using root logger
        stdout_logger = StreamToLogger(logging.getLogger("stdout"), logging.INFO)
        sys.stdout = stdout_logger

        # Redirect stderr to log at ERROR level using root logger
        stderr_logger = StreamToLogger(logging.getLogger("stderr"), logging.ERROR)
        sys.stderr = stderr_logger
        print(f"INFO [LoggingConfig]: stdout/stderr redirected.", file=stdout_logger) # Use the new stdout


    # Mark as configured for this process
    _logging_configured = True
    logging._process_id = os.getpid() # Store process ID
    # Use logger now that basic handlers are set up
    logging.getLogger("LoggingConfig").info(f"Logging configured for Node {node_id}. Level: {logging.getLevelName(log_level)}. Log file: {main_log_file}")

# --- Function to get logger ---
def get_logger(name):
     """Gets a logger instance. Assumes setup_node_logging has been called."""
     return logging.getLogger(name)