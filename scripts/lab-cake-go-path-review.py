"""Review frozen IPv4 passage and TCP evidence without network commands."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("path_review", Path(__file__).with_name("lab_cake_go_path_review.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = model.review(args.artifacts)
        print(json.dumps({k: result[k] for k in ("state", "source_commit", "results")}, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"Relecture IPv4 refusée : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
