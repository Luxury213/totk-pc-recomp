# Adapted from arnaldolima1/totk-recomp tools/achievements.py read_byml
# @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT).
# Copyright (c) 2026 Valiantsin Dzerakh; runtime/third_party/licenses/totk-recomp.txt.
"""BYML values needed by the local co-op model converter; no achievement subsystem."""
import struct


def read_byml(data):
    if len(data)<16 or data[:2] not in (b'YB',b'BY'):
        raise ValueError('not a BYML document')
    e='<' if data[:2]==b'YB' else '>'
    bo='little' if e=='<' else 'big'

    def take(off,n):
        if off<0 or n<0 or off+n>len(data): raise ValueError('truncated BYML')
        return data[off:off+n]

    def unpack(fmt,off):
        return struct.unpack(e+fmt,take(off,struct.calcsize(e+fmt)))

    keys_at,strings_at,root=unpack('III',4)

    def strtab(off):
        if not off: return []
        head=take(off,4)
        if head[0]!=0xc2: raise ValueError('invalid BYML string table')
        n=int.from_bytes(head[1:],bo)
        if n>len(data)//4: raise ValueError('excessive BYML string count')
        offsets=unpack(f'{n+1}I',off+4)
        result=[]
        for start,end in zip(offsets,offsets[1:]):
            raw=take(off+start,end-start)
            terminator=raw.find(b'\0')
            if terminator<0: raise ValueError('unterminated BYML string')
            result.append(raw[:terminator].decode('utf-8'))
        return result

    keys,strings=strtab(keys_at),strtab(strings_at)
    active=set()
    budget=max(1,len(data))

    def value(t,raw):
        if t==0xa0:
            if raw>=len(strings): raise ValueError('invalid BYML string index')
            return strings[raw]
        if t==0xd0: return bool(raw)
        if t==0xd1: return struct.unpack(e+'i',struct.pack(e+'I',raw))[0]
        if t==0xd2: return struct.unpack(e+'f',struct.pack(e+'I',raw))[0]
        if t==0xd3: return raw
        if t in (0xd4,0xd5,0xd6): return unpack({0xd4:'q',0xd5:'Q',0xd6:'d'}[t],raw)[0]
        if t==0xff: return None
        if t not in (0xc0,0xc1,0x20,0x21,0xa1): raise ValueError('unsupported BYML value')
        return node(raw,t)

    def node(off,expected=None):
        nonlocal budget
        if off in active or len(active)>=64 or budget<=0: raise ValueError('recursive/excessive BYML nodes')
        t=take(off,4)[0]
        n=int.from_bytes(data[off+1:off+4],bo)
        if expected is not None and expected!=t: raise ValueError('inconsistent BYML node')
        if n>len(data) or n>budget: raise ValueError('excessive BYML node count')
        budget-=n+1; active.add(off)
        try:
            if t==0xc0:
                types=take(off+4,n); vals=off+4+((n+3)&~3)
                take(vals,4*n)
                return [value(types[i],unpack('I',vals+4*i)[0]) for i in range(n)]
            if t==0xc1:
                take(off+4,8*n); out={}
                for i in range(n):
                    p=off+4+8*i; index=int.from_bytes(data[p:p+3],bo)
                    if index>=len(keys): raise ValueError('invalid BYML key index')
                    out[keys[index]]=value(data[p+3],unpack('I',p+4)[0])
                return out
            if t in (0x20,0x21):
                stride,key_format= (8,'I') if t==0x20 else (12,'Q')
                types=take(off+4+stride*n,n); take(off+4,stride*n)
                return {unpack(key_format,off+4+stride*i)[0]:
                        value(types[i],unpack('I',off+stride*i+stride)[0]) for i in range(n)}
            if t==0xa1: return bytes(take(off+8,unpack('I',off+4)[0]))
            raise ValueError(f'unsupported BYML node {t:#x}')
        finally:
            active.remove(off)

    return node(root)
