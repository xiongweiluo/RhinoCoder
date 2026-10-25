"""CPU boot-session/PID identity controls; no native host effects."""
import copy
from types import SimpleNamespace
import pytest
from plugin.rhino_listener import c5_reuse_mac_scope as module


@pytest.mark.parametrize('change',['valid','boot_session','uid','start','embedded_pid','wall_microseconds','missing_uuid'])
def test_stable_identity_rejects_new_boot_uid_or_process_without_using_observed_wall_microseconds(monkeypatch,change):
    process={'pid':44652,'uid':501,'start_time_utc_to_whole_second':'2026-10-11T16:14:32Z',
        'mac_boot_epoch_seconds':1790688926,'mac_boot_microseconds':281231,
        'mac_boot_session_uuid':'F873EC8A-960B-4B86-B35E-65A973D84E99'}
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        if argv[-1]=='kern.bootsessionuuid':
            return SimpleNamespace(stdout=('00000000-0000-0000-0000-000000000000' if change=='boot_session'
                                          else process['mac_boot_session_uuid'])+'\n')
        if argv[-1]=='uid=':return SimpleNamespace(stdout='502' if change=='uid' else '501')
        assert argv[-1]=='lstart=' and kwargs['env']['TZ']=='UTC'
        return SimpleNamespace(stdout='Sun Oct 11 16:14:33 2026' if change=='start' else 'Sun Oct 11 16:14:32 2026')
    monkeypatch.setattr(module.subprocess,'run',run)
    monkeypatch.setattr(module.os,'getpid',lambda:999 if change=='embedded_pid' else 44652)
    if change=='wall_microseconds':process['mac_boot_microseconds']=347198
    if change=='missing_uuid':process.pop('mac_boot_session_uuid')
    if change in ('valid','wall_microseconds'):module.verify_process_identity(process,embedded=True)
    else:
        with pytest.raises(ValueError):module.verify_process_identity(process,embedded=True)
    assert all('kern.boottime' not in argv for argv in calls)
