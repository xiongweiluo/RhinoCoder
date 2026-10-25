"""Prospective tail evidence/cleanup only. No grants, native/model loaders or retry."""
from plugin.rhino_listener.c5_research_native import require


from plugin.rhino_listener.c5_slot_tail_policy import enabled


def error_record(error, stage):
    # Fixed phase/type fields only; never export arbitrary private exception text.
    name = type(error).__name__
    known = {"KeyboardInterrupt", "EOFError", "TimeoutError", "NativeError",
             "PermissionError", "RuntimeError", "ValueError", "TypeError",
             "FormalRunError", "ConsentError", "CleanupEvidenceError"}
    return {"stage": stage, "error_type": name if name in known else "OtherError",
            "code": ("stopped_database_backup_unverified" if isinstance(error, CleanupEvidenceError)
                     else "step_failed_no_retry"),
            "replay_allowed": False}


class SigningSceneDrift(RuntimeError):
    slot_scope = "global"
    code = "shared_environment_pollution"


class CleanupEvidenceError(RuntimeError):
    tail_code = "stopped_database_backup_unverified"

    def __init__(self, receipt):
        self.cleanup_receipt = receipt
        super().__init__(self.tail_code)


def stop_known_child(adapter, slot_id, backup, publish):
    """Actual closed/stopped proof releases current even if later backup fails.

    had_failure is retained business/safety evidence, never erased. It cannot
    alone turn an acknowledged stop into an unknown active hook or grant next
    slot permission. The independent raw/health audit still controls that.
    """
    require(adapter.current == slot_id and adapter._tail_closed.get(slot_id),
            "slot_tail_stop_requires_known_close")
    value = adapter.channels[slot_id].control("stop")
    require(value.get("status") == "stopped"
            and value.get("hook_removed_in_same_callback") is True
            and type(value.get("had_failure")) is bool,
            "slot_tail_stop_receipt_incomplete")
    # Close receipt established fixture registry/key absence; stop established
    # observer removal. Record the actual cleanup before fallible disk backup.
    adapter.current = None
    adapter._tail_stopped[slot_id] = value
    try:
        directory = adapter.state / slot_id
        publish(directory, "database-backups.json", {
            n: backup(directory, n) for n in ("consent", "fixture")})
    except (KeyboardInterrupt, SystemExit, PermissionError) as error:
        error.cleanup_receipt = value
        raise
    except Exception as error:
        raise CleanupEvidenceError(value) from error
    return value
