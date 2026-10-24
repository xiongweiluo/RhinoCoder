#!/usr/bin/env python3
"""Stage an unapproved public slot package only; no grant/state/model creation."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_c5_slot_tail_package import assemble, encoded, SPEC, RUNTIME


def payload():
    docs = assemble()
    spec, freeze = docs[SPEC], docs[RUNTIME]
    files = {
        n: encoded(docs[n]) if n in docs else (ROOT / n).read_bytes()
        for n in freeze["source_files"]
    }
    files[RUNTIME] = encoded(freeze)
    return spec, freeze, files


def stage(endpoint):
    import tools.stage_c5_run_package as common

    common.payload = payload
    return common.stage(endpoint)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint", choices=("mac", "gpu"))
    print(json.dumps(stage(parser.parse_args().endpoint), sort_keys=True))
