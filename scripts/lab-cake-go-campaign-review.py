"""Relire un dossier de campagne figé sans commande réseau ni certificat natif."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

spec=importlib.util.spec_from_file_location('campaign_native_review',Path(__file__).with_name('lab_cake_go_campaign_native_review.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=model.review(args.artifacts)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except Exception as error:
        print(f'Relecture de campagne refusée : {error}',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
