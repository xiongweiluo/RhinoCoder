"""Independent pinned public manifest read, stdlib only; stdout, no writes."""
import hashlib
import json
from pathlib import Path

PATH = Path('/data/RhinoCoder-c5/base-snapshot-manifest.json')
PIN = '5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd'

raw = PATH.read_bytes()
if not 0 < len(raw) < 65536 or hashlib.sha256(raw).hexdigest()!=PIN:
    raise ValueError('pinned public manifest drift')
print(json.dumps({'base_manifest_raw_hex':raw.hex(),'base_manifest_sha256':PIN}))
