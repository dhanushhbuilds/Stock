"""python -m app.engines.signal_lab.train  — fit the research direction model used by Signal Lab."""

import json

from app.core.config import get_settings
from app.core.db import get_session
from app.engines.signal_lab.service import train_direction_model

if __name__ == "__main__":
    print(json.dumps(train_direction_model(next(get_session()), get_settings()), indent=2))
