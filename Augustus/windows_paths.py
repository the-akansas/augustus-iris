"""Windows filesystem paths without relying on global LongPathsEnabled."""
import os
from pathlib import Path

def filesystem_path(value):
    text=os.path.abspath(os.fspath(value))
    if os.name=='nt' and not text.startswith('\\\\?\\'):
        text=('\\\\?\\UNC\\'+text[2:]) if text.startswith('\\\\') else ('\\\\?\\'+text)
    return Path(text)

def launch_cwd(value):
    path=filesystem_path(value)
    # CreateProcessW retains a short-CWD restriction independently of file I/O.
    return path if len(str(path))<240 else Path(os.getcwd())


def legacy_process_path(value):
    """Old .NET AppDomain rejects extended-path prefixes, even on short paths."""
    text=os.fspath(value)
    if text.startswith('\\\\?\\UNC\\'):
        return '\\\\'+text[8:]
    if text.startswith('\\\\?\\'):
        return text[4:]
    return text

def sqlite_readonly_uri(value):
    """Encode the filesystem path as a URI path, never as an authority.

    Keep the Windows device prefix for paths longer than MAX_PATH. Escaping
    backslashes, question marks and hashes prevents URI reinterpretation.
    mode=ro preserves read-only access and never creates missing databases.
    """
    from urllib.parse import quote
    return 'file:' + quote(str(filesystem_path(value)), safe='/') + '?mode=ro'
