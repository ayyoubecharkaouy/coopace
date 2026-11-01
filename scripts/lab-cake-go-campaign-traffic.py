"""Private process entry for the six-phase Go/CAKE campaign traffic driver."""

import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("campaign_driver", Path(__file__).with_name("lab_cake_go_campaign_traffic.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

if __name__ == "__main__":
    sys.exit(model.main())
