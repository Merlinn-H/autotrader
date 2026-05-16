from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
