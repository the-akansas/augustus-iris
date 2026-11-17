"""Versioned room invitations. Data only: no executable paths or commands."""
import base64,hashlib,ipaddress,json,re
from pathlib import Path
from coordinator import PROTOCOL,BUILD
PREFIX='AUGMP1.'
KEYS={'protocol','build','session','scenario','host','port','invite','engine_sha256'}
def address(value):
 if not isinstance(value,str):raise ValueError('invalid server address')
 try:ip=ipaddress.IPv4Address(value)
 except ipaddress.AddressValueError:raise ValueError('invalid server address') from None
 if ip.is_unspecified or ip.is_multicast or ip.is_reserved or str(ip)=='255.255.255.255':raise ValueError('invalid server address')
 return str(ip)
def port(value,ephemeral=False):
 if type(value)!=int or not (0 if ephemeral else 1)<=value<=65535:raise ValueError('invalid server port')
 return value
def engine_hash():return hashlib.sha256((Path(__file__).parent/'augustus-mp-ui.exe').read_bytes()).hexdigest()
def validate(data,check_engine=True):
 if not isinstance(data,dict) or set(data)!=KEYS:raise ValueError('invalid room invitation')
 if type(data['protocol'])!=int or data['protocol']!=PROTOCOL or data['build']!=BUILD:raise ValueError('incompatible room version')
 for key,length in [('session',32),('scenario',64),('invite',64),('engine_sha256',64)]:
  if not isinstance(data[key],str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}',data[key]):raise ValueError('invalid room invitation')
 address(data['host']);port(data['port'])
 if check_engine and data['engine_sha256']!=engine_hash():raise ValueError('incompatible game executable')
 return dict(data)
def encode(data):
 raw=json.dumps(validate(data),separators=(',',':')).encode('ascii')
 return PREFIX+base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
def decode(code):
 if not isinstance(code,str):raise ValueError('invalid room invitation')
 code=code.strip()
 if not code.startswith(PREFIX) or len(code)>4096:raise ValueError('invalid room invitation')
 body=code[len(PREFIX):]
 if not re.fullmatch('[A-Za-z0-9_-]+',body):raise ValueError('invalid room invitation')
 try:raw=base64.b64decode(body+'='*((-len(body))%4),altchars=b'-_',validate=True);data=json.loads(raw)
 except (ValueError,UnicodeError):raise ValueError('invalid room invitation') from None
 return validate(data)
