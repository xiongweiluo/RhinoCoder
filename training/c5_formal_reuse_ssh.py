"""Pinned authenticated transport only. No authentication creation or fallback."""
import os
from pathlib import Path
import re
import shlex
import stat
from plugin.rhino_listener.c5_research_native import require
from plugin.rhino_listener.c5_formal_reuse_scope import REMOTE_SOURCE,REMOTE_ENV,file_sha
from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS

def argv(spec,mode,attempt):
    require(mode in ('serve','stop','export-supervisor') and type(attempt) is int and 1<=attempt<=(spec.get('run_package',{}).get('policy',{}).get('global_preexposure_loads_max',3)),
        'formal_reuse_fixed_remote_action')
    host,user,port=spec['ssh_host'],spec['ssh_user'],spec['ssh_port']
    require(type(host) is str and re.fullmatch(r'[A-Za-z0-9.-]{1,253}',host)
        and host[0]!='-' and user=='linux' and type(port) is int and 1<=port<=65535,
        'formal_reuse_actual_endpoint_required')
    for name in ('ssh_socket','ssh_known_hosts_file'):
        p=Path(spec[name]);require(p.is_absolute() and p.resolve()==p and '..' not in p.parts,'formal_reuse_auth_path')
    alias=spec['ssh_host_key_alias']
    require(type(alias) is str and re.fullmatch(r'[A-Za-z0-9.\[\]:_-]{1,280}',alias),'formal_reuse_host_key_alias')
    command=shlex.join([str(REMOTE_ENV/'bin/python3.11'),*GPU_FLAGS,
        str(REMOTE_SOURCE/('tools/c5_formal_reuse_control.py' if 'run_package' in spec and mode!='serve' else 'tools/run_c5_formal_reuse_worker.py')),mode,'--attempt',str(attempt)])
    return ['/usr/bin/ssh','-F','/dev/null','-T','-S',spec['ssh_socket'],'-o','BatchMode=yes',
        '-o','ControlMaster=no','-o','ProxyCommand=/usr/bin/false','-o','StrictHostKeyChecking=yes',
        '-o','UpdateHostKeys=no','-o','UserKnownHostsFile='+spec['ssh_known_hosts_file'],
        '-o','HostKeyAlias='+alias,'-o','ConnectTimeout=15','-p',str(port),user+'@'+host,
        'cd '+shlex.quote(str(REMOTE_SOURCE))+' && '+command]

def verify(spec,freeze):
    require(file_sha('/usr/bin/ssh')==freeze['ssh_executable_sha256']
        and file_sha(spec['ssh_known_hosts_file'])==spec['ssh_known_hosts_file_sha256'],
        'formal_reuse_transport_code_or_host_key_drift')
    p=Path(spec['ssh_socket']);info=p.lstat()
    require(p.resolve()==p and stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid()
        and info.st_nlink==1 and not info.st_mode&0o077,'formal_reuse_existing_authenticated_socket_required')
    return {'device':info.st_dev,'inode':info.st_ino}
