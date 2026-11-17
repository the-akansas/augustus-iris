"""Download immutable completed saves without blocking the clock's sole writer.

Only poll(), on the bridge thread, accepts a result. The download thread owns a
separate Client and never publishes native mailboxes or acknowledges succession.
"""
import threading
import time
import uuid
from types import SimpleNamespace

from city_client import Client
from save_replica import download

_slots = threading.BoundedSemaphore(2)


def recovery_save(state,saved):
    """Copy the newest eligible checkpoint, even if a newer file exists without custody."""
    throne=state.get('throne')
    if throne is not None:return throne.get('handover_save')
    return saved['complete']['id'] if saved.get('complete') else None


class Cancelled(Exception):
    pass


KEEP = 1


def prune(bridge, keep=KEEP):
    """This session's copies (host-backup-<session>-<id>): only the newest stays, manual or automatic (user
    2026-11-15: "수동저장이든 자동저장이든 게임당 최신1개만"; each copy holds every city's save). A copy without a
    recorded kind (an older version) and the copies the succession names are never removed."""
    import shutil
    prefix = 'host-backup-' + bridge.client.session + '-'
    copies = []
    for path in bridge.root.parent.glob(prefix + '*'):
        suffix = path.name[len(prefix):]
        if not suffix.isdigit() or not path.is_dir():
            continue
        try:
            kind = (path / 'save-kind.txt').read_text(encoding='ascii').strip()
        except OSError:
            continue
        if kind in ('auto', 'manual'):
            copies.append((int(suffix), path))
    plan = getattr(bridge, 'recovery_plan', None) or {}
    named = {getattr(bridge, 'replicated_id', None), getattr(bridge, 'succession_id', None), plan.get('save_id')}
    for sid, path in sorted(copies)[:-keep] if keep else sorted(copies):
        if sid not in named:
            shutil.rmtree(path, ignore_errors=True)


class Replicas:
    def __init__(self):
        self.job = None
        self.identity = None
        self.closed = False
        self.retry_after = 0

    def close(self):
        self.closed = True
        if self.job:
            self.job.cancel.set()

    def poll(self, bridge, sid):
        if self.closed or bridge.departed:
            return
        c = bridge.client
        identity = (c.session, c.city, c.token, c.address, c.scenario,
                    str(bridge.root.resolve()), getattr(bridge, 'layout_version', None))
        if self.identity != identity:
            if self.job:
                self.job.cancel.set()
            if self.identity is not None:
                bridge.replicated_id = None
                bridge.succession_armed = False
                bridge.succession_id = None
                bridge.recovery_plan = None
            self.identity = identity
            self.retry_after = 0
        job = self.job
        if job and job.done.is_set():
            if job.identity == identity and not job.cancel.is_set():
                if job.error is None:
                    bridge.replicated_id = job.sid
                else:
                    # A failed local replica is not evidence that the host left.
                    from network_diagnostics import record
                    record(bridge.root, 'replica_failed', reason=type(job.error).__name__)
                    self.retry_after = time.monotonic() + 5
            self.job = None
        # Pruned when what the bridge holds on to changes: a new copy, or the succession moving to it.
        held = (getattr(bridge, 'replicated_id', None), getattr(bridge, 'succession_id', None))
        if held[0] is not None and held != getattr(self, 'pruned_for', None):
            self.pruned_for = held
            prune(bridge)
        if (self.job or not sid or sid == getattr(bridge, 'replicated_id', None)
                or time.monotonic() < self.retry_after):
            return
        job = SimpleNamespace(identity=identity, sid=sid, cancel=threading.Event(),
                              done=threading.Event(), error=None)
        # Capture credentials now, never read the mutable bridge from the worker.
        client = Client(bridge.root / ('replica-client-' + uuid.uuid4().hex),
                        c.session, c.city, c.token, c.address, c.scenario)
        target = SimpleNamespace(root=bridge.root, config={'session': c.session}, client=client)

        def check():
            if job.cancel.is_set():
                raise Cancelled()

        def run():
            acquired = False
            try:
                while not acquired:
                    check()
                    acquired = _slots.acquire(timeout=0.1)
                check()
                download(target, sid, check=check)
                check()
            except Exception as error:
                job.error = error
            finally:
                if acquired:
                    _slots.release()
                job.done.set()

        job.thread = threading.Thread(target=run, name='completed-save-replica', daemon=True)
        self.job = job
        job.thread.start()
