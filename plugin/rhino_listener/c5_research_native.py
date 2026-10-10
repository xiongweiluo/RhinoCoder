"""C5 twelve-tool native headless backend, Python 3.9 compatible.

Trusted dispatch implementation only: NOT a Listener route, consent grant or
standalone executable. The signed/durable research controller must authorize
each call before dispatch. Never switches ActiveDoc or scriptcontext.doc.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading

from .candidate_alias_scene import _all_objects, _writable_layer

CORE = frozenset({"boolean_difference", "create_box", "create_cylinder", "create_sphere",
    "get_bounding_box", "get_scene_summary", "group_objects", "move_object", "rotate_object",
    "scale_object", "set_object_color", "set_object_layer"})
READS = frozenset({"get_bounding_box", "get_scene_summary"})
SCHEMA_SHA = "4b5710c2b7f13513fd3355654d22bff6b5631be53ba3bbd20472c09063f40bf6"
GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


class NativeError(RuntimeError):
    pass


def require(ok, reason):
    if not ok: raise NativeError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _schema_value(value, schema):
    if "anyOf" in schema:
        return any(_schema_value(value, s) for s in schema["anyOf"])
    kind = schema.get("type")
    if kind == "null": return value is None
    if kind == "string": return isinstance(value, str)
    if kind == "integer": return type(value) in (int, float) and math.isfinite(value) and value == int(value)
    if kind == "number": return type(value) in (int, float) and math.isfinite(value)
    if kind == "array": return isinstance(value, list) and len(value) <= 16 and all(_schema_value(v, schema["items"]) for v in value)
    raise NativeError("unsupported frozen schema node")


def validate_native_arguments(operation, arguments, schemas):
    require(set(schemas) == CORE and digest(schemas) == SCHEMA_SHA, "original core schema differs")
    require(operation in CORE and isinstance(arguments, dict), "unsupported operation/arguments")
    schema = schemas[operation]
    require(set(arguments) <= set(schema["properties"]) and set(schema.get("required", [])) <= set(arguments), "argument fields differ")
    require(all(_schema_value(value, schema["properties"][name]) for name, value in arguments.items()), "argument schema differs")
    # These are execution safety constraints, not a changed model schema or
    # an argument repair. Invalid values are rejected, never default-filled.
    for name, value in arguments.items():
        if type(value) in (int, float):
            require(math.isfinite(value) and abs(value) <= 100000, "unsafe numeric bound")
        if isinstance(value, str):
            require(0 < len(value) <= 80 and not any(ord(c) < 32 for c in value) and not GUID.search(value), "unsafe string/physical ID")
    if operation.startswith("create_"):
        require(all(value > 0 for value in arguments.values()), "nonpositive dimensions")
    for name in ("object_ids", "input0_ids", "input1_ids"):
        if name in arguments:
            values = arguments[name]
            require(bool(values) and len(values) == len(set(values)) and all(0 < len(v) <= 80 and not GUID.search(v)
                and not any(ord(c) < 32 for c in v) for v in values), "invalid alias set")
    for name in ("axis", "center_point", "scale_factor"):
        value = arguments.get(name)
        if value is not None:
            require(len(value) == 3 and all(abs(v) <= 100000 for v in value), "invalid vector")
    if arguments.get("axis") is not None:
        require(any(v != 0 for v in arguments["axis"]), "zero rotation axis")
    if "scale_factor" in arguments:
        require(all(v > 0 for v in arguments["scale_factor"]), "nonpositive scale")
    if operation == "set_object_color":
        require(all(0 <= arguments[c] <= 255 for c in ("r", "g", "b")), "color outside RGB range")
    if operation == "boolean_difference":
        require(not set(arguments["input0_ids"]) & set(arguments["input1_ids"]), "overlapping boolean roles")
    return json.loads(canonical(arguments))


def active_content_digest(doc):
    """Same declared R content-only scope; not entire 3dm/camera/table proof."""
    import Rhino
    options = Rhino.FileIO.SerializationOptions()
    options.WriteUserData = True
    objects = sorted((str(o.Id), o.Geometry.ToJSON(options), o.Attributes.ToJSON(options)) for o in _all_objects(doc))
    layers = sorted((str(l.Id), str(l.Name), str(l.ParentLayerId), bool(l.IsVisible), bool(l.IsLocked), str(l.Color))
                    for l in doc.Layers if not l.IsDeleted)
    return digest({"unit": str(doc.ModelUnitSystem), "objects": objects, "layers": layers,
        "absolute_tolerance": float(doc.ModelAbsoluteTolerance), "angle_tolerance": float(doc.ModelAngleToleranceRadians)})


def point(value):
    return [float(value.X), float(value.Y), float(value.Z)]


class NativeDoc:
    def __init__(self, fixture, active, schemas):
        import Rhino
        require(Rhino.RhinoApp.IsOnMainThread and active is not None and fixture is not None, "UI documents required")
        require(int(fixture.RuntimeSerialNumber) != int(active.RuntimeSerialNumber)
                and bool(fixture.IsHeadless) and not fixture.Path, "isolated unsaved headless fixture required")
        require(set(schemas) == CORE and digest(schemas) == SCHEMA_SHA, "original schema required")
        self.doc, self.active, self.schemas = fixture, active, schemas
        self.serial = int(fixture.RuntimeSerialNumber)
        self.active_serial = int(active.RuntimeSerialNumber)
        self.thread = threading.get_ident()
        self.initial_active_sha = active_content_digest(active)
        self.closed = False
        self.counter = 0
        self.guard()

    def guard(self):
        import Rhino
        require(not self.closed and threading.get_ident() == self.thread and Rhino.RhinoApp.IsOnMainThread, "closed/non-UI research fixture")
        active = Rhino.RhinoDoc.ActiveDoc
        require(active is not None and int(active.RuntimeSerialNumber) == self.active_serial
                and int(self.doc.RuntimeSerialNumber) == self.serial and bool(self.doc.IsHeadless)
                and not self.doc.Path and str(self.doc.ModelUnitSystem) == "Millimeters", "document scope drift")
        require(active_content_digest(active) == self.initial_active_sha, "active content changed")

    def objects(self):
        self.guard()
        objects = _all_objects(self.doc)
        require(len(objects) <= 16, "fixture object budget exceeded")
        aliases = [o.Attributes.Name for o in objects]
        require(all(isinstance(a, str) and 0 < len(a) <= 80 and not GUID.search(a) for a in aliases)
                and len(aliases) == len(set(aliases)), "fixture aliases not unique")
        return {o.Attributes.Name: o for o in objects}

    def target(self, alias, *, write=True):
        indexed = self.objects()
        require(alias in indexed, "unknown target alias")
        obj = indexed[alias]
        require(not obj.IsReference and (not write or obj.IsNormal and _writable_layer(self.doc, obj.Attributes.LayerIndex)), "target not writable")
        return obj

    def readback(self):
        import Rhino
        self.guard()
        prior_digest = active_content_digest(self.doc)
        rows = []
        options = Rhino.FileIO.SerializationOptions()
        options.WriteUserData = True
        for alias, obj in sorted(self.objects().items()):
            brep = obj.Geometry
            require(isinstance(brep, Rhino.Geometry.Brep) and brep.IsValid, "non-Brep/invalid research solid")
            bbox = brep.GetBoundingBox(True)
            mass = Rhino.Geometry.VolumeMassProperties.Compute(brep)
            require(bbox.IsValid and mass is not None and math.isfinite(float(mass.Volume)), "native mass/bounds unavailable")
            try:
                groups = sorted(self.doc.Groups.GroupName(int(i)) for i in (obj.Attributes.GetGroupList() or []))
                color = obj.Attributes.ObjectColor if str(obj.Attributes.ColorSource) == "ColorFromObject" else self.doc.Layers[obj.Attributes.LayerIndex].Color
                rows.append({"alias": alias, "min": point(bbox.Min), "max": point(bbox.Max),
                    "volume": float(mass.Volume), "centroid": point(mass.Centroid), "solid": bool(brep.IsSolid),
                    "face_count": int(brep.Faces.Count), "edge_count": int(brep.Edges.Count),
                    "vertices": sorted(point(v.Location) for v in brep.Vertices),
                    "layer": str(self.doc.Layers[obj.Attributes.LayerIndex].FullPath),
                    "color": [int(color.R), int(color.G), int(color.B)], "groups": groups,
                    "geometry_sha256": hashlib.sha256(brep.ToJSON(options).encode()).hexdigest()})
            finally:
                mass.Dispose()
        require(active_content_digest(self.doc) == prior_digest, "scene changed during native readback")
        self.guard()
        return {"unit": "Millimeters", "objects": rows,
            "groups": {g: sorted(row["alias"] for row in rows if g in row["groups"])
                       for g in sorted({g for row in rows for g in row["groups"]})}}

    def semantic_scene(self):
        native = self.readback()
        return {**native, "objects": [{k: row[k] for k in ("alias", "min", "max", "layer", "color", "groups")}
                                       for row in native["objects"]]}

    def _add(self, brep, kind):
        import System
        require(brep is not None and brep.IsValid and brep.IsSolid and len(self.objects()) < 16, "invalid/new object budget")
        self.counter += 1
        alias = kind+"-"+str(self.counter)
        require(alias not in self.objects(), "new alias conflict")
        attrs = self.doc.CreateDefaultAttributes()
        attrs.Name = alias
        oid = self.doc.Objects.AddBrep(brep, attrs)
        require(oid != System.Guid.Empty, "Rhino add failed")
        return alias

    def _layer(self, name):
        import Rhino
        require(all(part.strip() and part == part.strip() for part in name.split("::")), "invalid layer path")
        parent = None
        full = []
        for part in name.split("::"):
            full.append(part)
            index = self.doc.Layers.FindByFullPath("::".join(full), -1)
            if index < 0:
                layer = Rhino.DocObjects.Layer()
                layer.Name = part
                if parent is not None: layer.ParentLayerId = parent.Id
                index = self.doc.Layers.Add(layer)
                require(index >= 0, "layer add failed")
            require(_writable_layer(self.doc, index), "layer not writable")
            parent = self.doc.Layers[index]
        return index

    def dispatch(self, operation, arguments):
        """Low-level trusted callback; signed controller must reserve first."""
        import Rhino
        import System
        self.guard()
        args = validate_native_arguments(operation, arguments, self.schemas)
        G = Rhino.Geometry
        if operation == "get_scene_summary": return self.semantic_scene()
        if operation == "get_bounding_box":
            row = next(r for r in self.readback()["objects"] if r["alias"] == self.target(args["object_id"], write=False).Attributes.Name)
            return {"object_id": args["object_id"], "min": row["min"], "max": row["max"],
                    "center": [(a+b)/2 for a,b in zip(row["min"],row["max"])]}
        if operation == "create_box":
            box = G.Box(G.Plane.WorldXY, G.Interval(0,args["width"]), G.Interval(0,args["depth"]), G.Interval(0,args["height"]))
            result = {"created_alias": self._add(box.ToBrep(), "box")}
        elif operation == "create_sphere":
            result = {"created_alias": self._add(G.Sphere(G.Point3d.Origin,args["radius"]).ToBrep(), "sphere")}
        elif operation == "create_cylinder":
            cylinder = G.Cylinder(G.Circle(G.Plane.WorldXY,args["radius"]),args["height"])
            result = {"created_alias": self._add(cylinder.ToBrep(True,True), "cylinder")}
        elif operation in {"move_object", "rotate_object", "scale_object"}:
            obj = self.target(args["object_id"])
            if operation == "move_object":
                transform = G.Transform.Translation(args["translate_x"],args["translate_y"],args["translate_z"])
            else:
                bbox = obj.Geometry.GetBoundingBox(True)
                center = G.Point3d(*args["center_point"]) if args.get("center_point") is not None else bbox.Center
                if operation == "rotate_object":
                    axis = G.Vector3d(*(args.get("axis") or [0,0,1]))
                    require(axis.Unitize(), "invalid rotation axis")
                    transform = G.Transform.Rotation(math.radians(args["angle_degrees"]),axis,center)
                else:
                    transform = G.Transform.Scale(G.Plane(center,G.Vector3d.ZAxis),*args["scale_factor"])
            geometry = obj.Geometry.DuplicateBrep()
            require(geometry.Transform(transform) and geometry.IsValid and geometry.IsSolid, "invalid transformed geometry")
            require(self.doc.Objects.Replace(obj.Id,geometry), "Rhino replacement failed")
            result = {"changed_alias": args["object_id"]}
        elif operation == "set_object_layer":
            obj = self.target(args["object_id"])
            attrs = obj.Attributes.Duplicate()
            attrs.LayerIndex = self._layer(args["layer_name"])
            require(self.doc.Objects.ModifyAttributes(obj.Id,attrs,True), "layer attribute commit failed")
            result = {"changed_alias": args["object_id"], "layer": args["layer_name"]}
        elif operation == "set_object_color":
            targets = [self.target(a) for a in args["object_ids"]]
            for obj in targets:
                attrs = obj.Attributes.Duplicate()
                attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
                attrs.ObjectColor = System.Drawing.Color.FromArgb(int(args["r"]),int(args["g"]),int(args["b"]))
                require(self.doc.Objects.ModifyAttributes(obj.Id,attrs,True), "color attribute commit failed")
            result = {"changed_aliases": args["object_ids"]}
        elif operation == "group_objects":
            targets = [self.target(a) for a in args["object_ids"]]
            name = args.get("group_name") or "C5-group-"+str(self.counter+1)
            require(self.doc.Groups.FindName(name) is None, "group name already exists")
            index = self.doc.Groups.Add(name)
            require(index >= 0, "group add failed")
            for obj in targets: require(self.doc.Groups.AddToGroup(index,obj.Id), "group membership failed")
            result = {"group_name": name, "members": sorted(args["object_ids"])}
        elif operation == "boolean_difference":
            first = [self.target(a) for a in args["input0_ids"]]
            second = [self.target(a) for a in args["input1_ids"]]
            require(all(isinstance(o.Geometry,G.Brep) and o.Geometry.IsSolid for o in first+second), "boolean solid inputs required")
            outputs = G.Brep.CreateBooleanDifference([o.Geometry for o in first],[o.Geometry for o in second],self.doc.ModelAbsoluteTolerance)
            require(outputs and all(b.IsValid and b.IsSolid for b in outputs), "boolean failed")
            require(len(self.objects())+len(outputs) <= 16, "boolean intermediate object budget")
            aliases = [self._add(b,"difference") for b in outputs]
            for obj in first+second: require(self.doc.Objects.Delete(obj.Id,True), "boolean input deletion failed")
            result = {"created_aliases": aliases, "removed_aliases": args["input0_ids"]+args["input1_ids"]}
        else: raise NativeError("operation not implemented")
        self.guard()
        return result

    def close(self):
        import Rhino
        self.guard()
        before = active_content_digest(Rhino.RhinoDoc.ActiveDoc)
        fixture_before_close = self.readback()
        self.doc.Dispose()
        self.closed = True
        require(Rhino.RhinoDoc.FromRuntimeSerialNumber(self.serial) is None, "fixture registry still live after disposal")
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None
                and int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)==self.active_serial,
                "active document identity changed during close")
        after = active_content_digest(Rhino.RhinoDoc.ActiveDoc)
        require(before == after == self.initial_active_sha, "active content drift during close")
        return {"fixture_serial": self.serial, "initial_active_sha256": self.initial_active_sha,
                "before_close_active_sha256": before, "after_close_active_sha256": after,
                "before_close_active_serial": self.active_serial,"after_close_active_serial": self.active_serial,
                "fixture_registry_absent": True,
                "fixture_before_close_native": fixture_before_close,
                "capture_scope": "same_ui_callback_before_and_after_fixture_close"}
