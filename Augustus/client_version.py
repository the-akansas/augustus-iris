"""Display-only client identity. Existing executable/build compatibility gate remains authoritative."""
import json,re
from functools import lru_cache
from pathlib import Path
from connection_config import engine_hash

def validate_info(info):
 if not isinstance(info,dict) or set(info)!={'upstream','package','engine'}:raise ValueError('invalid version info')
 if not all(isinstance(v,str) and re.fullmatch('[a-zA-Z0-9._-]{1,64}',v) for v in info.values()):raise ValueError('invalid version info')
 if not re.fullmatch('[0-9a-f]{64}',info['engine']):raise ValueError('invalid version info')
 return dict(info)

@lru_cache(maxsize=1)
def local_info():
 d=json.loads(Path(__file__).with_name('release.json').read_text(encoding='utf-8-sig'))
 return validate_info(dict(upstream=d['upstream_version']+'-'+d['upstream_commit'][:9],package=d['internal_build']+'-'+d['package_revision'],engine=engine_hash()))

def label(info):
 if not info:return '버전 확인 대기'
 return 'Augustus '+info['upstream']+' / '+info['package']+' / '+info['engine'][:8]
