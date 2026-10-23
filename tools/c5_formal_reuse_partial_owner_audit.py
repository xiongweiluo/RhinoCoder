#!/usr/bin/env python3
"""Owner private TTY: read existing evidence only; no field execution authority."""
import argparse,hashlib,importlib,importlib.util,json,os,runpy,stat,sys,tempfile,shutil
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
ORIGINAL=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r2-source')
EVIDENCE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r2-state/preload-3')
OUTPUT=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r2-partial-audit-state')
SPEC='dff43f351b64159341c363c5156578c9da0ad3820a20d8a9baa46c7cde18d9c1'
RUNTIME='8f946c2efd02397e04e1fbc143410785371d82748a84c1939f334ba866e495ed'
FILES={'owner.py','core.py'}
def require(value,code):
    if not value:raise ValueError(code)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def file_sha(path):
    require(path.resolve()==path and path.is_file() and not path.is_symlink(),'partial_audit_file_identity')
    return hashlib.sha256(path.read_bytes()).hexdigest()
def public_json(path):
    require(path.resolve()==path and path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=2097152,'partial_audit_public_file')
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,'partial_audit_duplicate_json_key');value[key]=item
        return value
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('partial_audit_nonfinite_json')))
def public_original():
    require(sys.flags.isolated and sys.dont_write_bytecode and Path(sys.executable).resolve()==Path('/opt/anaconda3/bin/python3.13'),
        'partial_audit_fixed_interpreter')
    spec=public_json(ORIGINAL/'eval/c5/reuse-formal-20261023-r2-spec.json')
    freeze=public_json(ORIGINAL/'eval/c5/reuse-formal-20261023-r2-runtime.json')
    require(digest(spec)==SPEC and digest(freeze)==RUNTIME and sys.version==freeze['mac_environment']['python']
        and sys.pycache_prefix==str(Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-d-bytecode-cache-must-remain-absent'))
        and not os.path.lexists(sys.pycache_prefix),'partial_audit_original_pair_and_runtime')
    def guard():
        require(digest(public_json(ORIGINAL/'eval/c5/reuse-formal-20261023-r2-spec.json'))==SPEC
            and digest(public_json(ORIGINAL/'eval/c5/reuse-formal-20261023-r2-runtime.json'))==RUNTIME
            and all(file_sha(ORIGINAL/name)==sha for name,sha in freeze['source_files'].items())
            and all(file_sha(ORIGINAL/name)==sha for name,sha in freeze['fixed_public_files'].items()),'partial_audit_original_public_bytes')
    guard();return spec,freeze,guard
def load_core(freeze):
    sys.path.insert(0,str(ORIGINAL))
    core=runpy.run_path(str(SOURCE/'core.py'),run_name='c5_partial_readonly_core')
    from training.c5_execution import load_config,load_pinned_tokenizer
    tokenizer=load_pinned_tokenizer(Path(freeze['tokenizer_dir']),config=load_config(ORIGINAL/'eval/c5/c5-engineering-config.json'))
    for name in ('training.c5_formal_reuse_joint_audit','training.c5_host_assurance_audit',
        'training.c5_lifecycle_joint_audit','training.c5_formal_reuse_evidence_audit',
        'training.c5_formal_reuse_runtime','training.c5_formal_reuse_admission','training.c5_rhino_adapter'):
        importlib.import_module(name)
    tokenizer.apply_chat_template([{'role':'user','content':'Public CPU-only audit closure probe'}],tokenize=False,add_generation_prompt=True)
    return core['audit_partial'],tokenizer
def environment():
    files={}
    from plugin.rhino_listener.c5_formal_reuse_origins import origin_path
    for module in tuple(sys.modules.values()):
        path=origin_path(module,sys.modules,require)
        if path is None:continue
        path=path.resolve(strict=True)
        if path.is_relative_to(ORIGINAL) or path.is_relative_to(SOURCE):continue
        files[str(path)]=file_sha(path)
    executable=Path(sys.executable).resolve(strict=True);files[str(executable)]=file_sha(executable)
    return {'python':sys.version,'executable':str(executable),'sys_path':list(sys.path),'readable_loaded_external_files':files,
        'kernel_and_unlisted_opaque_runtime_trusted_not_byte_proven':True}
def verify_environment(current,expected):
    require(all(current[k]==expected[k] for k in ('python','executable','sys_path',
        'kernel_and_unlisted_opaque_runtime_trusted_not_byte_proven')),'partial_audit_environment_identity')
    require(all(expected['readable_loaded_external_files'].get(path)==sha
        for path,sha in current['readable_loaded_external_files'].items()),'partial_audit_unfrozen_loaded_origin')
def evidence_inventory(root):
    require(root.resolve()==root and root.is_dir() and not root.is_symlink(),'partial_audit_evidence_directory')
    result={};total=0
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(),'partial_audit_evidence_symlink')
        if path.is_dir():continue
        info=path.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and not(stat.S_IMODE(info.st_mode)&0o022) and 0<=info.st_size<=33554432,'partial_audit_evidence_file_scope')
        if path.name.endswith('-audit.sqlite3-wal'):
            require(info.st_size==0,'partial_audit_unbound_nonempty_sqlite_wal')
        total+=info.st_size
        require(total<=134217728 and len(result)<20000,'partial_audit_evidence_population_cap')
        result[path.relative_to(root).as_posix()]={'sha256':file_sha(path),'bytes':info.st_size,
            'mode':stat.S_IMODE(info.st_mode),'inode':info.st_ino,'mtime_ns':info.st_mtime_ns}
    return result
def copy_evidence(original,destination):
    before=evidence_inventory(original)
    destination.mkdir(mode=0o700)
    for name,value in before.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        raw=(original/name).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==value['sha256'],'partial_audit_copy_source_changed')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw)
        require(file_sha(target)==value['sha256'],'partial_audit_copy_bytes')
    require(evidence_inventory(original)==before,'partial_audit_original_changed_during_copy')
    return before
def publish(name,value):
    require(name=='owner-public-partial-audit-summary.json','partial_audit_public_output_name')
    raw=(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    require(len(raw)<=131072,'partial_audit_bounded_summary')
    if OUTPUT.exists():
        require(OUTPUT.resolve()==OUTPUT and OUTPUT.stat().st_uid==os.getuid() and stat.S_IMODE(OUTPUT.stat().st_mode)==0o700,
            'partial_audit_existing_output_identity')
    else:OUTPUT.mkdir(mode=0o700)
    path=OUTPUT/name
    if path.exists():require(path.read_bytes()==raw,'partial_audit_existing_summary_changed');return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('inspect-runtime','audit'))
    parser.add_argument('--review-sha256');args=parser.parse_args();stage='public_scope'
    try:
        if args.mode=='audit':require(sys.stdin.isatty() and sys.stderr.isatty(),'partial_audit_owner_private_terminal_required')
        spec,freeze,original_guard=public_original()
        review=None
        if args.mode=='audit':
            review=public_json(SOURCE/'review-runtime.json')
            require(digest(review)==args.review_sha256 and review['source_files'].keys()==FILES
                and review['original_spec_sha256']==SPEC and review['original_runtime_sha256']==RUNTIME,
                'partial_audit_review_binding')
            require(all(file_sha(SOURCE/name)==sha for name,sha in review['source_files'].items()),'partial_audit_review_code')
        audit,tokenizer=load_core(freeze)
        if args.mode=='inspect-runtime':
            value=environment();allowed=dict(freeze['mac_environment']['file_sha256'])
            for path,sha in value['readable_loaded_external_files'].items():
                require(path not in allowed or allowed[path]==sha,'partial_audit_original_environment_drift')
                allowed[path]=sha
            require(all(file_sha(Path(path))==sha for path,sha in allowed.items()),'partial_audit_allowed_environment_bytes')
            probe_count=len(value['readable_loaded_external_files']);value['readable_loaded_external_files']=allowed
            print(json.dumps({'status':'public_readonly_audit_runtime_inspected','environment':value,
                'probe_external_file_count':probe_count,'closed_allowed_external_files':len(allowed),
                'private_evidence_reads':0,'model_or_rhino_calls':0},sort_keys=True));return 0
        def guard():
            original_guard()
            require(digest(public_json(SOURCE/'review-runtime.json'))==args.review_sha256
                and all(file_sha(SOURCE/name)==sha for name,sha in review['source_files'].items())
                and all(file_sha(Path(path))==sha for path,sha in review['environment']['readable_loaded_external_files'].items()),
                'partial_audit_review_runtime_changed')
            verify_environment(environment(),review['environment'])
        guard();stage='existing_private_evidence'
        from plugin.rhino_listener.c5_research_channel import read_json
        def on_stage(value):
            nonlocal stage
            stage=value;print('C5_READONLY_PARTIAL_AUDIT '+value,flush=True)
        if not OUTPUT.exists():OUTPUT.mkdir(mode=0o700)
        require(OUTPUT.resolve()==OUTPUT and OUTPUT.stat().st_uid==os.getuid()
            and stat.S_IMODE(OUTPUT.stat().st_mode)==0o700,'partial_audit_private_output_directory')
        with tempfile.TemporaryDirectory(prefix='readonly-evidence-',dir=OUTPUT) as temporary:
            copied=Path(temporary)/'preload-3';before=copy_evidence(EVIDENCE,copied)
            summary=audit(copied,read_json(copied,'private-cases.json'),spec,freeze,tokenizer,source_guard=guard,on_stage=on_stage)
            require(evidence_inventory(EVIDENCE)==before,'partial_audit_original_changed_after_audit')
            summary.update(original_source_or_evidence_modified=False,evidence_copy_bytes_verified=True,
                original_evidence_file_count=len(before),original_evidence_inventory_sha256=digest(before),
                sqlite_reader_sidecars_confined_to_disposable_private_copy=True)
        guard();summary.update(review_runtime_sha256=args.review_sha256,actor='repository_owner',
            audit_kind='additional_retrospective_partial_not_original_full40')
        publish('owner-public-partial-audit-summary.json',summary)
        print('C5_READONLY_PARTIAL_AUDIT_COMPLETE_NO_RESEARCH_RESTART',flush=True)
        print(json.dumps(summary,sort_keys=True));return 0
    except BaseException as error:
        code=str(error)
        if not(code.startswith('partial_') and code.replace('_','').isascii() and code.replace('_','').isalnum()):code=type(error).__name__
        print(json.dumps({'status':'readonly_partial_audit_refused','stage':stage,'error_code':code,
            'private_content_included':False,'research_restarted':False}),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
