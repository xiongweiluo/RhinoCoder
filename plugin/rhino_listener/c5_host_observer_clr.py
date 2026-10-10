"""Actual CLR/macOS metadata adapter. Construction is an approved host effect.

Import is stdlib-only. Never constructs RhinoDoc, models, tools or task data.
Non-file/dyld-cache/dynamic artifacts are explicit unresolved evidence.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import threading
import time
from pathlib import Path

from .c5_research_native import active_content_digest, digest, require, _all_objects


class ClrObserverBackend:
    def __init__(self, spec, source_root):
        import System
        import Rhino
        from System.Runtime.CompilerServices import RuntimeHelpers
        from System.Reflection.Emit import AssemblyBuilder, AssemblyBuilderAccess
        self.System,self.Rhino=System,Rhino
        require(sys.platform=='darwin' and str(Rhino.RhinoApp.Version)==spec['expected_rhino_version']
            and list(sys.version_info[:2])==spec['expected_embedded_python_major_minor'],
            'frozen observer Rhino/Python/platform differs')
        self.AssemblyBuilder,self.Access=AssemblyBuilder,AssemblyBuilderAccess
        self.domain=System.AppDomain.CurrentDomain
        self.spec,self.root=spec,Path(source_root)
        self.refs,self.lock,self.queue,self.dropped,self.errors=[],threading.RLock(),[],0,[]
        self.canaries,self.canary_builders,self.handler,self.subscribed={},{},None,False
        self.helper=RuntimeHelpers
        self.process_identity=digest({'pid':os.getpid(),'adapter_instance':str(time.monotonic_ns()),
            'executable':sys.executable,'runtime':str(Rhino.RhinoApp.Version)})
        self.active=Rhino.RhinoDoc.ActiveDoc
        require(Rhino.RhinoApp.IsOnMainThread and self.active is not None
            and len(_all_objects(self.active))==0, 'observer needs empty main-thread Rhino document')
        self.dyld=ctypes.CDLL(None)
        self.dyld._dyld_image_count.argtypes=[];self.dyld._dyld_image_count.restype=ctypes.c_uint32
        self.dyld._dyld_get_image_name.argtypes=[ctypes.c_uint32]
        self.dyld._dyld_get_image_name.restype=ctypes.c_char_p

    def identity(self, assembly):
        with self.lock:
            for index,old in enumerate(self.refs):
                if self.System.Object.ReferenceEquals(old,assembly): return 'clr-%04d'%index
            require(len(self.refs)<1024, 'observer CLR reference bound exhausted')
            self.refs.append(assembly)
            return 'clr-%04d'%(len(self.refs)-1)

    def file_record(self, origin):
        """Only approved code roots/extensions; never hash arbitrary data files."""
        path=Path(str(origin))
        roots=[Path(p) for p in self.spec['code_read_roots']]
        allowed=path.is_absolute() and any(path.is_relative_to(p) for p in roots)
        allowed=allowed and (path.suffix.lower() in {'.py','.pyc','.so','.dll','.dylib','.rhp','.pyd'}
            or str(path) in self.spec['code_read_exact_files'])
        if not allowed:
            return {'origin_sha256':hashlib.sha256(str(origin).encode()).hexdigest(),
                'origin':None,'file_sha256':None,'state':'outside_approved_code_roots_or_type'}
        try:
            path=path.resolve(strict=True)
            require(any(path.is_relative_to(p) for p in roots), 'observer resolved code origin escape')
            require(path.is_file(), 'observer origin not file')
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1048576),b''):h.update(block)
            return {'origin_sha256':hashlib.sha256(str(origin).encode()).hexdigest(),
                'origin':str(path),'file_sha256':h.hexdigest(),'state':'file_backed_bytes_only'}
        except (OSError,RuntimeError):
            return {'origin_sha256':hashlib.sha256(str(origin).encode()).hexdigest(),
                'origin':None,'file_sha256':None,'state':'unreadable_or_shared_cache_not_file_proven'}

    def assembly_row(self, assembly):
        row={'instance_id':self.identity(assembly),'name':str(assembly.FullName),'dynamic':bool(assembly.IsDynamic),
            'probe_canary_role':None,'module_version_id':None,'file':None,'visible_type_count':None,
            'visible_types':[],'surface_sha256':None,'inspection_errors':[],
            'surface_scope':'reflection_visible_only_not_dynamic_method_or_emitted_byte_proof'}
        for role,value in self.canaries.items():
            if self.System.Object.ReferenceEquals(value,assembly):row['probe_canary_role']=role
        try:row['module_version_id']=str(assembly.ManifestModule.ModuleVersionId)
        except BaseException as exc:row['inspection_errors'].append('MVID:'+type(exc).__name__)
        if not row['dynamic']:
            try:row['file']=self.file_record(str(assembly.Location))
            except BaseException as exc:row['inspection_errors'].append('Location:'+type(exc).__name__)
        else:
            try:
                types=list(assembly.GetTypes())
                require(len(types)<=256, 'observer dynamic type limit')
                row['visible_type_count']=len(types)
                for kind in types:
                    methods=list(kind.GetMethods(self.System.Reflection.BindingFlags.Public |
                        self.System.Reflection.BindingFlags.NonPublic | self.System.Reflection.BindingFlags.Instance |
                        self.System.Reflection.BindingFlags.Static | self.System.Reflection.BindingFlags.DeclaredOnly))
                    require(len(methods)<=512, 'observer dynamic method surface limit')
                    row['visible_types'].append({'name':str(kind.FullName),
                        'methods':sorted(str(m) for m in methods),
                        'constructors':sorted(str(c) for c in kind.GetConstructors()),
                        'method_bytes_or_hidden_dynamic_methods_verified':False})
                row['visible_types'].sort(key=lambda item:item['name'])
            except BaseException as exc:row['inspection_errors'].append('Reflection:'+type(exc).__name__)
        row['surface_sha256']=digest({k:v for k,v in row.items() if k!='surface_sha256'})
        return row

    def snapshot(self):
        require(self.Rhino.RhinoApp.IsOnMainThread and self.Rhino.RhinoDoc.ActiveDoc is not None
            and int(self.Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)==int(self.active.RuntimeSerialNumber),
            'observer active Rhino document switched')
        assemblies=[self.assembly_row(a) for a in self.domain.GetAssemblies()]
        require(len(assemblies)<=1024, 'observer assembly inventory bound')
        count=int(self.dyld._dyld_image_count())
        require(count<=4096, 'observer native image bound')
        images=[]
        for index in range(count):
            origin=self.dyld._dyld_get_image_name(index)
            require(origin is not None, 'observer native image identity missing')
            images.append(self.file_record(origin.decode('utf-8','strict')))
        origins=[]
        for name,module in tuple(sys.modules.items()):
            origin=getattr(module,'__file__',None)
            if origin:
                origins.append({'module':name,'python_object_identity':str(id(module)),
                    'file':self.file_record(origin),'origin_is_absolute':Path(str(origin)).is_absolute()})
        limits=['DynamicMethods and emitted bytes are not proven by reflection.',
            'AssemblyLoad does not observe mutations inside an existing assembly.',
            'Snapshot comparison does not prove absence of transient between-snapshot mutations.',
            'Existing interactive host is not a controlled clean baseline.']
        if any(row['inspection_errors'] for row in assemblies):limits.append('Some assembly metadata is not inspectable.')
        if any(row['file_sha256'] is None for row in images):limits.append('Some native images lack on-disk byte proof.')
        return {'process_identity':self.process_identity,'python_origins':sorted(origins,key=lambda r:r['module']),
            'assemblies':sorted(assemblies,key=lambda r:r['instance_id']),
            'native_images':sorted(images,key=lambda r:r['origin_sha256']),
            'active_sha256':active_content_digest(self.active),'active_serial':int(self.active.RuntimeSerialNumber),
            'active_object_count':len(_all_objects(self.active)),'inspection_limits':limits}

    def subscribe(self):
        require(self.handler is None, 'observer subscription cannot retry')
        def capture(sender,args):
            try:
                assembly=args.LoadedAssembly
                event={'event':'AssemblyLoad','instance_id':self.identity(assembly),
                    'name':str(assembly.FullName),'dynamic':bool(assembly.IsDynamic)}
                with self.lock:
                    if len(self.queue)>=256:self.dropped+=1
                    else:self.queue.append(event)
            except BaseException as exc:
                with self.lock:
                    if len(self.errors)<256:self.errors.append(type(exc).__name__)
                    else:self.dropped+=1
        self.handler=self.System.AssemblyLoadEventHandler(capture)
        self.domain.AssemblyLoad+=self.handler
        self.subscribed=True

    def unsubscribe(self):
        require(self.handler is not None, 'no exact observer delegate for cleanup')
        self.domain.AssemblyLoad-=self.handler
        self.subscribed=False

    def drain_events(self):
        with self.lock:
            value={'events':list(self.queue),'dropped':self.dropped,'errors':list(self.errors)}
            self.queue.clear();self.errors.clear();self.dropped=0
            return value

    def create_canary(self,role):
        require(role in {'subscribed','detached'} and role not in self.canaries,
            'two exact observer canaries only; no replay')
        name=self.spec['canary_names'][role]
        require(not any(str(a.GetName().Name)==name for a in self.domain.GetAssemblies()),
            'observer canary name already exists')
        # Non-collectible, bounded, single-main-thread canaries. They remain
        # until host exit; no GC/unload assumption or forced host restart.
        builder=self.AssemblyBuilder.DefineDynamicAssembly(self.System.Reflection.AssemblyName(name),self.Access.Run)
        mvid=str(builder.ManifestModule.ModuleVersionId)
        rows=[a for a in self.domain.GetAssemblies() if bool(a.IsDynamic)
            and str(a.FullName)==str(builder.FullName) and str(a.ManifestModule.ModuleVersionId)==mvid]
        require(len(rows)==1, 'created observer canary runtime instance ambiguous')
        self.canaries[role]=rows[0]
        self.canary_builders[role]=builder

    def add_empty_type(self):
        assembly=self.canary_builders['subscribed']
        module=assembly.DefineDynamicModule('C5ObserverEmptyModule')
        module.DefineType('C5ObserverEmptyType',self.System.Reflection.TypeAttributes.Public).CreateType()
