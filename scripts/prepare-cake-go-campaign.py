"""Freeze campaign inputs only; native launcher and independent replay follow."""

import argparse
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("campaign_preparation", Path(__file__).with_name("prepare-cake-go-active.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, help="dossier neuf ; son parent doit exister")
    args = parser.parse_args(argv)
    try:
        model.prepare(args.artifacts, campaign=True)
        return 0
    except Exception as error:
        print(f"Préparation de campagne refusée : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
