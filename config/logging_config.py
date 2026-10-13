# config/logging_config.py
import logging 
import os
from datetime import datetime

# 1. Generate unique execution log files using timestamp strings
LOG_FILE = f"{datetime.now().strftime('%m_%d_%Y_%H_%M_%S')}.log"

# 2. Build the target logs storage path safely relative to the application base folder
logs_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(logs_dir, exist_ok=True)

# 3. Define the full absolute log file file destination path
LOG_FILE_PATH = os.path.join(logs_dir, LOG_FILE)

# 4. Apply standard structured formatting rules globally
logging.basicConfig(
    filename=LOG_FILE_PATH,
    format="[ %(asctime)s ] %(lineno)d %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# 5. Export an independent, public logger object for the entire project to import
logger = logging.getLogger("agent_system")

# Write initial boot confirmation trace into the active file stream
logger.info("System Logger has been initialized successfully.")
