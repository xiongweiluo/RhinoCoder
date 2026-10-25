#!python3
"""Release only after run_path returned/restored temporary entry modules."""
import runpy
import sys
from pathlib import Path


def main():
    sys.dont_write_bytecode=True
    root=Path(__file__).resolve().parents[1]
    result=runpy.run_path(str(root/'tools/run_c5_reuse_rhino_entry.py'),run_name='__main__')
    result['ENTRY_RETURN_BARRIER'].release_after_entry_return()


if __name__=='__main__':main()
