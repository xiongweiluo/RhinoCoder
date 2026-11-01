#! python 3
"""Single frozen wrapper: release only after the host entry returns."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    result = runpy.run_path(str(Path(__file__).resolve().with_name('run_lora_development_rhino.py')), run_name='__main__')
    result['SESSION'].release()
