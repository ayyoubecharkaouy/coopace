"""Private subprocess entry; use only under the lab supervisor's owned group."""

import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("cake_go_traffic", Path(__file__).with_name("lab_cake_go_traffic.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

if __name__ == "__main__":
    sys.exit(model.main())
