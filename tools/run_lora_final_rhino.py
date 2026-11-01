#! python 3
"""Same proved Idle/headless host entry, admitted only by a separate final grant."""
from pathlib import Path
import runpy

if __name__=='__main__':
    entry=runpy.run_path(str(Path(__file__).resolve().with_name('run_lora_common_probe_rhino.py')))
    SESSION=entry['start'](final=True)
    SESSION.release()
