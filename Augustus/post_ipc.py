"""Bounded native packet codec. No save files, sockets, or waits here."""
import struct,zlib
REQUEST=260
RESPONSE=64136
def request(run,epoch,nonce,roster,owner,sequence,command=None,receipt_epoch=0):
    if not 0<sequence<2**32 or not 0<=owner<8:raise ValueError('identity')
    fields=[bytes.fromhex(x) for x in (run,epoch,nonce,roster)]
    if list(map(len,fields))!=[16,16,16,32]:raise ValueError('identity width')
    # roster is canonical hex text to match native SAV identity.
    p=bytearray(b'MPI1'+b''.join(fields[:3])+struct.pack('<I',receipt_epoch)+roster.encode('ascii'))
    p+=struct.pack('<III',owner,sequence,(3 if command and command.get("compact") else 2 if command and command.get("transport") else int(command is not None)))
    if command is not None:
        ident=command['id'].encode('ascii')
        if not ident or len(ident)>=96 or b'\0' in ident:raise ValueError('command id')
        p+=ident.ljust(96,b'\0')+struct.pack('<iiii',command['peer'],command['step'],command['resource'],command['amount'])
    else:p+=bytes(112)
    p+=struct.pack("<III",*command["transport"]) if command and command.get("transport") else bytes(12)
    return bytes(p)+struct.pack('<I',zlib.crc32(p))
def response(data,expected):
    if len(data)!=RESPONSE or data[:4]!=b'MPR1' or data[4:128]!=expected[4:128]:raise ValueError('stale native response')
    if struct.unpack_from('<I',data,len(data)-4)[0]!=zlib.crc32(data[:-4]):raise ValueError('native CRC')
    result=struct.unpack_from('<i',data,128)[0]
    if result not in (-2,0,1):raise ValueError('native result')
    return result,data[132:-4]
