"""Injected CPU loader controls; torch/PEFT/models are namespace fixtures."""
import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import training.c5_reuse_gpu_loader as loader


def test_missing_entry_guard_rejects_before_any_torch_import_or_model(monkeypatch,tmp_path):
    before=sys.modules.get('torch')
    def reject():raise ValueError('CPU missing frozen entry')
    with pytest.raises(ValueError,match='missing frozen entry'):
        loader.load(tmp_path,{},reject,lambda:None,runtime={},plan={})
    assert sys.modules.get('torch') is before


@pytest.mark.parametrize('kind',['valid','changed_after_load'])
def test_original_loader_settings_and_postload_asset_closure_before_readiness(monkeypatch,tmp_path,kind):
    import training.c5_execution as execution
    import training.c5_modelbridge_runtime as environment
    events=[];base=NS(config=NS(use_cache=True));tokenizer=object()
    class Model:
        def eval(self):events.append('eval')
        @contextlib.contextmanager
        def disable_adapter(self):
            events.append('adapter_disabled');yield;events.append('adapter_restored')
    model=Model()
    cuda=NS(is_available=lambda:True,is_bf16_supported=lambda:True,mem_get_info=lambda:(20*1024**3,24*1024**3),
            manual_seed_all=lambda s:events.append(('cuda_seed',s)),reset_peak_memory_stats=lambda:events.append('reset_peak'))
    torch=NS(cuda=cuda,bfloat16='cpu_bfloat16_fixture',manual_seed=lambda s:events.append(('seed',s)),
             backends=NS(cuda=NS(matmul=NS(allow_tf32=False))))
    def quant(**kw):events.append(('quant',kw));return kw
    def pretrained(snapshot,**kw):events.append(('base',snapshot,kw));return base
    def prepare(value,**kw):assert value is base;events.append(('prepare',kw));return value
    def attach(value,path,**kw):assert value is base;events.append(('adapter',path,kw));return model
    monkeypatch.setitem(sys.modules,'torch',torch)
    monkeypatch.setitem(sys.modules,'transformers',NS(AutoModelForCausalLM=NS(from_pretrained=pretrained),BitsAndBytesConfig=quant))
    monkeypatch.setitem(sys.modules,'peft',NS(PeftModel=NS(from_pretrained=attach),prepare_model_for_kbit_training=prepare))
    def config(p):events.append(('config',p));return {'cpu_fixture':True}
    monkeypatch.setattr(execution,'load_config',config)
    monkeypatch.setattr(execution,'load_pinned_tokenizer',lambda p,config:tokenizer)
    monkeypatch.setattr(execution,'generation',lambda m,t,p,s:events.append(('generation',m is model,t is tokenizer,p,s)) or {'cpu_fixture':True})
    monkeypatch.setattr(environment,'verify_loaded_environment',lambda *_:events.append('dependency_guard'))
    def preflight(*_):
        assert 'eval' in events;events.append('postload_asset_guard')
        return {'file':'changed' if kind=='changed_after_load' else 'frozen'}
    monkeypatch.setattr(loader,'preflight',preflight)
    if kind=='changed_after_load':
        with pytest.raises(ValueError,match='load_asset_closure'):
            loader.load(tmp_path,{'file':'frozen'},lambda:None,lambda:None,runtime={},plan={})
        assert not any(type(e) is tuple and e[0]=='generation' for e in events);return
    t,g,route,check=loader.load(tmp_path,{'file':'frozen'},lambda:None,lambda:None,runtime={},plan={})
    assert t is tokenizer and base.config.use_cache is False and torch.backends.cuda.matmul.allow_tf32 is True
    assert ('seed',20260928) in events and ('cuda_seed',20260928) in events
    assert ('prepare',{'use_gradient_checkpointing':False}) in events
    assert ('adapter',loader.ADAPTER,{'local_files_only':True,'is_trainable':False}) in events
    item=next(e for e in events if type(e) is tuple and e[0]=='base')
    assert item[1]==loader.SNAPSHOT and item[2]['local_files_only'] is True and item[2]['trust_remote_code'] is False
    assert item[2]['device_map']=={'':0} and item[2]['dtype']=='cpu_bfloat16_fixture'
    assert item[2]['quantization_config']=={'load_in_4bit':True,'bnb_4bit_quant_type':'nf4',
        'bnb_4bit_use_double_quant':True,'bnb_4bit_compute_dtype':'cpu_bfloat16_fixture'}
    with route('base'):assert g('CPU prompt','selector')=={'cpu_fixture':True}
    with route('lora'):pass
    assert events.count('adapter_disabled')==events.count('adapter_restored')==1
    with pytest.raises(ValueError):route('other')
