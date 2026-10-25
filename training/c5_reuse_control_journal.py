"""Bounded durable supervisor/stop evidence, separate from generation rows."""
import os
from pathlib import Path

from plugin.rhino_listener.c5_research_channel import private_directory,publish_json
from training.c5_reuse_evidence import exact,require,sha,canonical,strict,ZERO
from training.c5_reuse_field_journal import read_record
from training.c5_reuse_field_scope import validate_binding

MAX_ROWS=32


class ControlJournal:
    def __init__(self,binding,role):
        validate_binding(binding)
        require((binding['endpoint']=='gpu' and role in ('supervisor','independent-stop','worker-lifecycle'))
                or (binding['endpoint']=='mac' and role=='controller-lifecycle'),'reuse_control_role')
        self.binding=strict(canonical(binding));self.role=role
        self.root=Path(binding['paths']['state_root'])/role
        self.root.mkdir(mode=0o700)
        self.identity=self.root.stat();self.rows=[];self.head=ZERO
        self.append('control_open',{'role':role,'binding':self.binding})

    def append(self,kind,payload):
        require(type(kind) is str and type(payload) is dict and len(self.rows)<MAX_ROWS,'reuse_control_capacity')
        fd=private_directory(self.root)
        try:
            opened=os.fstat(fd)
            require((opened.st_dev,opened.st_ino)==(self.identity.st_dev,self.identity.st_ino)
                    and set(os.listdir(fd))=={'raw-%04d.json'%i for i in range(len(self.rows))},'reuse_control_population')
        finally:os.close(fd)
        if self.rows:
            previous,_=read_record(self.root,'raw-%04d.json'%(len(self.rows)-1))
            require(previous==self.rows[-1],'reuse_control_previous_drift')
        row={'seq':len(self.rows),'previous_sha256':self.head,'scope_sha256':sha(self.binding),
             'kind':kind,'payload':payload}
        row['record_sha256']=sha(row)
        publish_json(self.root,'raw-%04d.json'%len(self.rows),row)
        observed,_=read_record(self.root,'raw-%04d.json'%len(self.rows))
        require(observed==row,'reuse_control_readback')
        self.rows.append(strict(canonical(row)));self.head=row['record_sha256']


def read_control(root,binding,role,*,head=None):
    fd=private_directory(root)
    try:
        names=set(os.listdir(fd));identity=os.fstat(fd)
    finally:os.close(fd)
    require(0<len(names)<=MAX_ROWS and names=={'raw-%04d.json'%i for i in range(len(names))},'reuse_control_disk_population')
    rows=[read_record(root,'raw-%04d.json'%i)[0] for i in range(len(names))]
    fd=private_directory(root)
    try:
        current=os.fstat(fd)
        require((current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino) and set(os.listdir(fd))==names,
                'reuse_control_disk_changed')
    finally:os.close(fd)
    replay_control(rows,binding,role,head=head)
    return rows


def replay_control(rows,binding,role,*,head=None):
    validate_binding(binding)
    require(type(rows) is list and 0<len(rows)<=MAX_ROWS,'reuse_control_raw_population')
    previous=ZERO
    for i,row in enumerate(rows):
        exact(row,('seq','previous_sha256','scope_sha256','kind','payload','record_sha256'))
        require(type(row['seq']) is int and row['seq']==i and row['previous_sha256']==previous
                and row['scope_sha256']==sha(binding)
                and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),'reuse_control_chain')
        previous=row['record_sha256']
    require(rows[0]['kind']=='control_open' and rows[0]['payload']=={'role':role,'binding':binding}
            and (head is None or head==previous),'reuse_control_binding_anchor')
    return previous
