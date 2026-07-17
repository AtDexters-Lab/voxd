from pathlib import Path

from platformdirs import user_config_dir, user_data_dir


CONFIG_DIR = Path(user_config_dir("voxd"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DATA_DIR = Path(user_data_dir("voxd"))
OUTPUT_DIR = DATA_DIR / "output"
RECORDINGS_DIR = DATA_DIR / "recordings"
LOG_DIR = DATA_DIR / "logs"

for directory in (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, RECORDINGS_DIR, LOG_DIR):
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)

for private_directory in (DATA_DIR, OUTPUT_DIR, RECORDINGS_DIR, LOG_DIR):
    private_directory.chmod(0o700)
