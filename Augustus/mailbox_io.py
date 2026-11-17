"""Atomic mailbox publication while the Windows game briefly holds readers open."""
import os
import time
from pathlib import Path

def publish_text(target, text):
    target = Path(target)
    temporary = target.with_suffix('.publish-tmp')
    temporary.write_text(text, encoding='utf-8', newline='')
    deadline = time.monotonic() + 2
    while True:
        try:
            os.replace(temporary, target)
            return
        except OSError as error:
            # CRT fopen readers can deny FILE_SHARE_DELETE until fclose.
            if getattr(error, 'winerror', None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def remove_file(target, timeout=2):
    """Wait for a short-lived CRT reader; never silently retain stale state."""
    target=Path(target);deadline=time.monotonic()+timeout
    while True:
        try:
            target.unlink(missing_ok=True)
            return
        except OSError as error:
            if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:
                raise
            time.sleep(.01)


def read_command(target):
    """A published command can still be briefly locked by Windows rename/CRT.

    Leave it intact and retry on the next poll; never replay a partially read
    command or wait on the game render thread.
    """
    try:
        return Path(target).read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except OSError as error:
        if getattr(error,'winerror',None) in (5,32,33) or isinstance(error,PermissionError):
            return None
        raise

_live_failures={}
def read_live_text(target):
    """Latest telemetry only; retry a locked/missing sample on the next poll."""
    try:
        text=Path(target).read_text(encoding='utf-8')
        _live_failures.pop(str(target),None)
        return text
    except FileNotFoundError:
        _live_failures.pop(str(target),None)
        return None
    except OSError as error:
        if isinstance(error,PermissionError) or getattr(error,'winerror',None) in (32,33):
            # Python's CRT may omit winerror for sharing violations. Bound the
            # grace interval so a genuine permission failure is never hidden.
            key=str(target);now=time.monotonic()
            if key not in _live_failures:
                if len(_live_failures)>=64:_live_failures.pop(next(iter(_live_failures)))
                _live_failures[key]=now
            if now-_live_failures[key]<2:return None
        raise
