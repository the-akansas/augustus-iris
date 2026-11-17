"""Short, shareable cause for a notice (user 2026-11-13: an army dispatch bug once showed an unrelated save/path
message; '적어도 어떤 오류인지는 알아야 수정을 할거 아니야'). One line, no local paths, kept short."""
import os,re,traceback

_PATH=re.compile(r"""(?:\\\\\?\\)?(?:[A-Za-z]:[\\/]|\\\\|/(?:home|tmp|mnt|Users|root)/)[^'"\s,)]*""")

def reason(text,limit=90):
    text=' '.join(str(text).split())
    text=_PATH.sub('<경로>',text)
    return text if len(text)<=limit else text[:limit-1]+'…'

def where(error):
    """'KeyError: 'flag' (army_bridge.py 120행)' - the type, the message and the last line of our own code."""
    frames=traceback.extract_tb(error.__traceback__) if error.__traceback__ else []
    ours=[f for f in frames if os.path.basename(f.filename).endswith('.py')]
    at=f' ({os.path.basename(ours[-1].filename)} {ours[-1].lineno}행)' if ours else ''
    message=reason(error,70)
    return type(error).__name__+(': '+message if message else '')+at
