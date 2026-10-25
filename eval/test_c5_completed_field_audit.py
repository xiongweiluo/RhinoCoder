"""Observed retained-clock bounds, original rejection and isolated verifier."""
import ast
import copy
import json
from pathlib import Path
import pytest
from training.c5_completed_field_gpu_audit import _budget
from training.c5_recovery_field_gpu_audit import _budget as original_budget
ROOT=Path(__file__).resolve().parents[1]
def fixture():return json.loads((ROOT/'eval/c5/recovery-attempt3-budget-audit-regression-20261014.json').read_bytes())
@pytest.mark.parametrize('phase',('launch','worker_settlement','supervisor_final'))
def test_actual_completed_observations_fit_both_bounds_without_recredit(phase):
    f=fixture();v=f['budgets'][phase];r=f['resources']
    assert v['start_epoch']==1791916117.781239 and v['reserved_wall_seconds']==86400
    assert v['start_epoch']+v['reserved_wall_seconds']>r['generation_cutoff_epoch']
    with pytest.raises(ValueError,match='recovery_audit_shared_wall_budget'):original_budget(v,r)
    _budget(v,r)
@pytest.mark.parametrize('change',('past_lease','past_shared_cap','negative_elapsed','changed_cap','wrong_flag','nan','boolean_epoch','changed_stop_reserve'))
def test_bad_observations_still_rejected(change):
    f=fixture();v=copy.deepcopy(f['budgets']['launch']);r=copy.deepcopy(f['resources'])
    if change=='past_lease':v['elapsed_wall_seconds']=r['generation_cutoff_epoch']-v['start_epoch']+1
    elif change=='past_shared_cap':r['generation_cutoff_epoch']=v['start_epoch']+90000;v['elapsed_wall_seconds']=86401;v['within_reserved_wall_seconds']=False
    elif change=='negative_elapsed':v['elapsed_wall_seconds']=-1
    elif change=='changed_cap':v['reserved_wall_seconds']+=1
    elif change=='wrong_flag':v['within_reserved_wall_seconds']=False
    elif change=='nan':v['elapsed_wall_seconds']=float('nan')
    elif change=='boolean_epoch':v['start_epoch']=True
    else:v['stop_reserve_seconds']=0
    with pytest.raises(ValueError):_budget(v,r)
def test_originally_full_reserved_window_remains_valid():
    f=fixture();r=f['resources'];v=f['budgets']['launch'];r['generation_cutoff_epoch']=v['start_epoch']+86400
    original_budget(v,r);_budget(v,r)
def test_only_budget_function_changed_original_frozen_verifier_unchanged():
    a=ast.parse((ROOT/'training/c5_recovery_field_gpu_audit.py').read_text());b=ast.parse((ROOT/'training/c5_completed_field_gpu_audit.py').read_text())
    def parts(tree):return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    x,y=parts(a),parts(b);assert set(x)==set(y) and {k for k in x if x[k]!=y[k]}=={'_budget'}

from types import ModuleType
from tools.review_c5_completed_field_audit import origin_path
def require(ok,reason):
    if not ok:raise ValueError(reason)
@pytest.mark.parametrize('kind',('ops','classes'))
def test_exact_typed_virtual_namespace_defining_source(kind):
    name='torch.'+kind;owner_name='torch._'+kind;owner=ModuleType(owner_name);owner.__file__='/frozen/torch/_'+kind+'.py'
    cls=type('_Ops' if kind=='ops' else '_Classes',(ModuleType,),{'__file__':'_'+kind+'.py'})
    setattr(owner,cls.__name__,cls);value=cls(name);torch=ModuleType('torch');setattr(torch,kind,value)
    modules={name:value,owner_name:owner,'torch':torch};assert str(origin_path(value,modules,require))==owner.__file__
    del modules[name]
    with pytest.raises(ValueError,match='virtual_namespace_identity'):origin_path(value,modules,require)
@pytest.mark.parametrize('name',('torch.ops','torch.classes'))
def test_relative_name_cannot_spoof_virtual_namespace(name):
    value=ModuleType(name);value.__file__='_ops.py'
    with pytest.raises(ValueError):origin_path(value,{name:value},require)
def test_unknown_relative_origin_stays_rejected():
    value=ModuleType('unknown');value.__file__='elsewhere.py'
    with pytest.raises(ValueError,match='unresolved_loaded_origin'):origin_path(value,{},require)
