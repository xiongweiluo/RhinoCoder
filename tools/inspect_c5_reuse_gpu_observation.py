import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

exe=Path(sys.executable).resolve()
btime=next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
receipt={'status':'readonly_current_environment_observation_not_execution_authority',
 'epoch':time.time(),'uid':os.getuid(),'python':sys.version,'executable':str(exe),
 'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'boot_epoch':btime,'clock_ticks_per_second':os.sysconf('SC_CLK_TCK'),
 'original_worker_43776_present':Path('/proc/43776').exists(),
 'expected_environment_exists':Path('/data/conda-envs/rhinocoder/bin/python').exists(),
 'model_or_rhino_calls':0,'private_evidence_reads':0,'remote_files_written':0}
for key,args in [('gpu',['nvidia-smi','--query-gpu=uuid,name,memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits']),
                 ('compute_processes',['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'])]:
 p=subprocess.run(args,capture_output=True,text=True)
 receipt[key]={'returncode':p.returncode,'rows':p.stdout.strip().splitlines()}
print(json.dumps(receipt,sort_keys=True))
