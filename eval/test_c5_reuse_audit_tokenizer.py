"""All six Mac audit tokenizer assets; CPU files only, no tokenizer loading."""
import copy
import hashlib
from pathlib import Path
import pytest
from plugin.rhino_listener import c5_reuse_mac_scope as module
from eval.test_c5_reuse_field_assets import records
from tools.check_c5_reuse_field_assets import check_assets


@pytest.mark.parametrize('change',['valid','drift','missing','extra','symlink','wrong_root','wrong_hash'])
def test_exact_public_tokenizer_population_and_each_byte_before_audit(tmp_path,monkeypatch,change):
    root=tmp_path/'public-tokenizer';root.mkdir()
    files={}
    for n in module.TOKENIZER_NAMES:
        raw=('CPU asset '+n).encode();(root/n).write_bytes(raw);files[n]=hashlib.sha256(raw).hexdigest()
    assets={'audit_tokenizer_dir':str(root),'audit_tokenizer_files':files}
    monkeypatch.setattr(module,'AUDIT_TOKENIZER_ROOT',root)
    target=root/'tokenizer.json'
    if change=='drift':target.write_bytes(b'other token ids')
    elif change=='missing':target.unlink()
    elif change=='extra':(root/'added_tokens.json').write_bytes(b'{}')
    elif change=='symlink':target.unlink();target.symlink_to(root/'config.json')
    elif change=='wrong_root':assets['audit_tokenizer_dir']=str(tmp_path/'another')
    elif change=='wrong_hash':assets['audit_tokenizer_files']['vocab.json']='0'*64
    if change=='valid':module.verify_audit_tokenizer(assets)
    else:
        with pytest.raises((ValueError,OSError)):module.verify_audit_tokenizer(assets)


@pytest.mark.parametrize('change',['valid','actual_drift','extra_file','wrong_path','not_exact','gpu_different'])
def test_independent_assets_join_binds_mac_copy_to_gpu_original(change):
    p,g,m=records();names=module.TOKENIZER_NAMES
    expected={n:'a'*64 for n in names};p['model_assets']['base_files']=expected.copy();g['base_files']=expected.copy()
    p['model_assets'].update(audit_tokenizer_dir='/CPU/public-tokenizer',audit_tokenizer_files=expected.copy())
    m['audit_tokenizer']={'directory':'/CPU/public-tokenizer','file_sha256':expected.copy(),'population_exact':True}
    if change=='actual_drift':m['audit_tokenizer']['file_sha256']['merges.txt']='0'*64
    elif change=='extra_file':m['audit_tokenizer']['file_sha256']['extra.json']='a'*64
    elif change=='wrong_path':m['audit_tokenizer']['directory']='/CPU/other'
    elif change=='not_exact':m['audit_tokenizer']['population_exact']=False
    elif change=='gpu_different':p['model_assets']['audit_tokenizer_files']['tokenizer.json']='0'*64;m['audit_tokenizer']['file_sha256']['tokenizer.json']='0'*64
    if change=='valid':assert check_assets(p,g,m)['supplied_actual_installed_asset_maps_verified']
    else:
        with pytest.raises(ValueError):check_assets(p,g,m)
