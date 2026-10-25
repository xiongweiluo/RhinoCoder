#! python 3
"""Read-only environment metadata. No subscriptions, documents or task access."""
import json
import Rhino
import System
doc=Rhino.RhinoDoc.ActiveDoc
count=None if doc is None else sum(1 for _ in doc.Objects.GetObjectList(Rhino.DocObjects.ObjectType.AnyObject))
groups=None if doc is None else int(doc.Groups.Count)
value={'pid':int(System.Diagnostics.Process.GetCurrentProcess().Id),
    'rhino_version':str(Rhino.RhinoApp.Version),'active_document_present':doc is not None,
    'active_document_serial':None if doc is None else int(doc.RuntimeSerialNumber),
    'active_object_count':count,'active_group_count':groups,
    'active_document_blank':count==0 and groups==0,
    'private_paths_or_geometry_included':False,'new_documents_created':0,
    'subscriptions_created':0,'native_dispatches':0,'model_calls':0}
print('C5_FORMAL_REUSE_READONLY_RHINO_ENVIRONMENT '+json.dumps(value,sort_keys=True))
