"""Keep control polling alive while a captured save crosses a slow connection.

The server remains responsible for credentials, checkpoint ID, exact tick and
duplicate-content validation. Cancellation cannot recall an already sent RPC.
Late replies never publish a clock or acknowledge another capture/session.
"""
import base64
import threading
import time
import uuid
from types import SimpleNamespace

from city_client import Client
from coordinator import MAX_SAVE
from network_diagnostics import record


class Upload:
    def __init__(self):
        self.job = None
        self.closed = False
        self.retry_after = 0
        self.key = None
        # The bridge loop and the clock pump's barrier fast lane both poll.
        self.lock = threading.RLock()

    def close(self):
        self.closed = True
        if self.job:
            self.job.cancel.set()

    def poll(self, bridge, pending, reported_ticks):
        with self.lock:
            return self._poll(bridge, pending, reported_ticks)

    def _poll(self, bridge, pending, reported_ticks):
        if self.closed or bridge.departed:
            return
        c = bridge.client
        key = ((c.session, c.city, c.token, c.address, c.scenario,
                getattr(bridge, 'layout_version', None), pending['id'], pending['ticks'])
               if pending else None)
        if key is None and self.job and not self.job.done.is_set():
            # A bridge pass may carry a save_status read before the barrier the
            # fast lane already serves; never cancel an in-flight upload for it.
            return
        if key != self.key:
            if self.job:
                self.job.cancel.set()
            self.key = key
            self.retry_after = 0
        job = self.job
        if job and job.done.is_set():
            if job.key == key and not job.cancel.is_set():
                if job.error is None:
                    bridge.uploaded.add(job.sid)
                    record(bridge.root, 'save_upload', outcome='ok')
                else:
                    record(bridge.root, 'save_upload', outcome='failed', reason=type(job.error).__name__)
                    self.retry_after = time.monotonic() + 5
            self.job = None
        if (self.job or not pending or pending['id'] in bridge.uploaded
                or reported_ticks != pending['ticks'] or time.monotonic() < self.retry_after):
            return
        marker = bridge.root / 'capture.txt'
        if not marker.exists():
            return
        sid, ticks = map(int, marker.read_text().split())
        if (sid, ticks) != (pending['id'], pending['ticks']):
            return
        path = bridge.root / ('capture-' + str(sid) + '.sav')
        client = Client(bridge.root / ('upload-client-' + uuid.uuid4().hex),
                        c.session, c.city, c.token, c.address, c.scenario)
        job = SimpleNamespace(key=key, sid=sid, cancel=threading.Event(),
                              done=threading.Event(), error=None)

        def run():
            try:
                if job.cancel.is_set():
                    return
                # Native capture uses an immutable ID-specific file. Bound the read
                # before allocating/base64 encoding it on this background thread.
                with path.open('rb') as f:
                    payload = f.read(MAX_SAVE + 1)
                if not payload or len(payload) > MAX_SAVE:
                    raise ValueError('snapshot size')
                if job.cancel.is_set():
                    return
                client.call('save_part', id=sid, ticks=ticks,
                            save=base64.b64encode(payload).decode('ascii'))
            except Exception as error:
                job.error = error
            finally:
                job.done.set()

        job.thread = threading.Thread(target=run, name='captured-save-upload', daemon=True)
        self.job = job
        job.thread.start()
