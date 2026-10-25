#!/usr/bin/env python3
"""Public candidate deployment only; state/grants/keys/claims are never made.

Verified files are reused, changed unapproved public bytes archived. Actual
formal state presence blocks all source replacement. No model or native call.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,MAC_SOURCE,MAC_STATE,REMOTE_SOURCE,REMOTE_STATE,REMOTE_ENV
from plugin.rhino_listener.c5_research_native import digest,require
from training.c5_formal_reuse_deployment import stage_local,verify

def payload():
    s=json.loads((ROOT/SPEC_FILE).read_bytes());r=json.loads((ROOT/FREEZE_FILE).read_bytes())
    files={n:(ROOT/n).read_bytes() for n in r['source_files']};files[FREEZE_FILE]=(ROOT/FREEZE_FILE).read_bytes()
    require(all(hashlib.sha256(files[n]).hexdigest()==h for n,h in r['source_files'].items()),
        'formal_reuse_stage_saved_source_drift')
    return s,r,files

def stage_mac():
    s,r,files=payload()
    stage_local(MAC_SOURCE,files,state_root=MAC_STATE,archive_root=MAC_SOURCE.parent/'reuse-formal-20261022-unapproved-source-archive')
    return verify(MAC_SOURCE,s,r)

def stage_gpu():
    s,r,files=payload()
    from training.c5_formal_reuse_ssh import argv,verify as verify_transport
    verify_transport(s,r)
    # The fixed Python bootstrap contains trusted public source functions only.
    tree=ast.parse((ROOT/'training/c5_formal_reuse_deployment.py').read_text())
    stage=ast.unparse(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='stage_local'))
    script='import sys,json,base64,hashlib,os,stat,zlib\nfrom pathlib import Path\n'
    script+='def require(ok,message):\n if not ok:raise ValueError(message)\n'
    script+=stage+'\n'
    script+='header=sys.stdin.buffer.readline(32)\nrequire(header.endswith(b"\\n") and header[:-1].isdigit(),"public_payload_header")\n'
    script+='length=int(header)\nrequire(0<length<=16777216,"compressed_public_payload_capacity")\n'
    script+='compressed=sys.stdin.buffer.read(length)\nrequire(len(compressed)==length,"complete_public_payload")\n'
    script+='decoder=zlib.decompressobj()\nraw=decoder.decompress(compressed,33554433)\n'
    script+='require(len(raw)<=33554432 and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,"public_payload_capacity")\nvalue=json.loads(raw)\n'
    script+='files={n:base64.b64decode(v,validate=True) for n,v in value["payload"].items()}\n'
    script+='root=Path('+repr(str(REMOTE_SOURCE))+')\n'
    script+='stage_local(root,files,state_root=Path('+repr(str(REMOTE_STATE))+'),archive_root=root.parent/"reuse-formal-20261022-unapproved-source-archive")\n'
    script+='sys.path.insert(0,str(root))\nfrom training.c5_formal_reuse_deployment import verify\n'
    script+='print(json.dumps(verify(root,value["spec"],value["runtime"]),sort_keys=True))\n'
    args=argv(s,'export-supervisor',1)[:-1]+[shlex.join([str(REMOTE_ENV/'bin/python3.11'),'-I','-B','-c',script])]
    body=json.dumps({'spec':s,'runtime':r,'payload':{n:base64.b64encode(raw).decode() for n,raw in files.items()}},
        separators=(',',':')).encode()
    require(len(body)<=33554432,'formal_reuse_bounded_public_payload')
    packed=zlib.compress(body,6)
    require(len(packed)<=16777216,'formal_reuse_bounded_compressed_payload')
    wire=str(len(packed)).encode()+b'\n'+packed
    value=subprocess.run(args,input=wire,capture_output=True,timeout=300,check=True)
    reply=json.loads(value.stdout)
    require(reply['spec_sha256']==digest(s) and reply['runtime_sha256']==digest(r)
        and reply['files']==len(files),'formal_reuse_actual_gpu_stage_receipt')
    return reply

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('endpoint',choices=('mac','gpu'));a=p.parse_args()
    print(json.dumps(stage_mac() if a.endpoint=='mac' else stage_gpu(),sort_keys=True))
