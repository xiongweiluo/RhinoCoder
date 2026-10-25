"""Standalone system-stdlib read-only asset check; no model imports or writes.

Run explicitly on the approved GPU endpoint with python3 -I -S -B and stdin.
It is an observation, not a grant, entrypoint or complete runtime freeze.
Cached bytecode is reported separately from the historical loadable inventory.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def file_sha(p):
 p=Path(p).resolve(strict=True)
 before=p.stat()
 h=hashlib.sha256()
 with p.open('rb') as stream:
  for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
 after=p.stat()
 assert all(getattr(before,k)==getattr(after,k) for k in
  ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink'))
 return h.hexdigest()

start=time.time()
manifest=Path('/data/RhinoCoder-c5/base-snapshot-manifest.json')
assert file_sha(manifest)=='5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd'
manifest_raw=manifest.read_bytes()
assert hashlib.sha256(manifest_raw).hexdigest()=='5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd'
m=json.loads(manifest_raw)
base=Path(m['snapshot_dir'])
assert base==Path('/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/c03e6d358207e414f1eca0bb1891e29f1db0e242')
assert len(m['file_sha256'])==14
base_files={n:file_sha(base/n) for n in sorted(m['file_sha256'])}
assert base_files==m['file_sha256']
adapter_root=Path('/data/c5-runs-20261001/formal/checkpoint-132')
adapter={'adapter_config.json':'8a776a47b085b787b7c7f3c9b068aed8c0f018278de2b94bf66130f5542d6d4f',
 'adapter_model.safetensors':'da8acdcde2671aa397534b35369fe4a84b9d150f80f7b7026a4366a770be2883'}
actual_adapter={n:file_sha(adapter_root/n) for n in adapter}
assert actual_adapter==adapter
env=Path('/data/conda-envs/rhinocoder')
site=env/'lib/python3.11/site-packages'
packages={}
distribution_files={}
missing=[]
for dist in importlib.metadata.distributions(path=[str(site)]):
 name=dist.metadata['Name']
 packages[name]=dist.version
 for relative in dist.files or []:
  p=Path(dist.locate_file(relative))
  if p.is_file():distribution_files[str(p.resolve())]=file_sha(p)
  else:missing.append(name+':'+str(relative))
stdlib={str(p.resolve()):file_sha(p) for p in sorted((env/'lib/python3.11').rglob('*'))
 if p.is_file() and 'site-packages' not in p.parts and p.suffix in ('.py','.pyc','.so')}
libpython={str(p.resolve()):file_sha(p) for p in sorted((env/'lib').glob('libpython*.so*')) if p.is_file()}
p=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.used,memory.total,utilization.gpu',
 '--format=csv,noheader,nounits'],capture_output=True,text=True)
assert p.returncode==0
def loadable(name):
 return '__pycache__' not in Path(name).parts and Path(name).suffix not in ('.pyc','.pyo')
normalized_distribution={str(Path(n).relative_to(env)):v for n,v in distribution_files.items() if loadable(n)}
normalized_stdlib={str(Path(n).relative_to(env)):v for n,v in stdlib.items() if loadable(n)}
target_runtime=subprocess.run([str(env/'bin/python3.11'),'-I','-S','-B','-c',
 'import sys,platform,json; print(json.dumps({"python":sys.version,"platform":platform.platform()}))'],
 capture_output=True,text=True,timeout=15,check=True)
print(json.dumps({'status':'current_public_assets_rehashed_not_execution_authority',
 'start_epoch':start,'finish_epoch':time.time(),
 'target_runtime':json.loads(target_runtime.stdout),
 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'gpu_rows':p.stdout.strip().splitlines(),'base_files':base_files,'adapter_files':actual_adapter,
 'base_manifest_sha256':file_sha(manifest),'base_manifest_raw_hex':manifest_raw.hex(),'base_files_match_pinned_manifest':True,
 'packages':packages,'distribution_file_sha256':distribution_files,'distribution_inventory_sha256':digest(distribution_files),
 'stdlib_file_sha256':stdlib,'stdlib_inventory_sha256':digest(stdlib),'libpython_file_sha256':libpython,
 'interpreter_sha256':file_sha(env/'bin/python'),'missing_metadata_files':sorted(missing),
 'historical_policy_distribution_inventory_sha256':digest(normalized_distribution),
 'historical_policy_distribution_files':len(normalized_distribution),
 'historical_policy_stdlib_inventory_sha256':digest(normalized_stdlib),
 'historical_policy_stdlib_files':len(normalized_stdlib),
 'cache_bytecode_files':len(distribution_files)-len(normalized_distribution)+len(stdlib)-len(normalized_stdlib),
 'historical_policy_missing_metadata_files':sorted(n for n in missing if loadable(n)),
 'model_loaded':False,'cuda_initialized_by_this_checker':False,'remote_files_written':0,'private_evidence_reads':0,
 'opaque_kernel_driver_and_host_not_byte_proven':True},sort_keys=True))
