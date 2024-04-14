import os

from platformdirs import user_cache_dir


APPLICATION_NAME = "spbot"
CACHE_DIR = os.environ.get("SPBOT_CACHE_DIR", user_cache_dir(APPLICATION_NAME))
