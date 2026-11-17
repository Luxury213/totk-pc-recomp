"""Prepare only requested equipment models from the user's RomFS, not the full armor library.

Uses the pinned MIT tools/link_figure.py reader/converter. Output is a private LNKA2
library for future attachment rendering; preparing assets does not enable gameplay.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from check_content import GENERATED_MARKER
from prepare_coop_figure import private_output

ROOT=Path(__file__).resolve().parents[1]
ACTOR=re.compile(r'Weapon_(?:Sword|Lsword|Spear|Shield|Bow)_[0-9][A-Za-z0-9_]*')
MODEL=re.compile(r'[A-Za-z0-9_]+\.[A-Za-z0-9_]+')


def select_actors(requested, available):
    names=sorted(set(requested))
    if not names or len(names)>16:
        raise ValueError('select between one and sixteen equipped actor names')
    for actor in names:
        if not isinstance(actor,str) or len(actor)>=48 or not ACTOR.fullmatch(actor):
            raise ValueError('invalid equipment actor name')
        if actor not in available or not MODEL.fullmatch(available[actor]):
            raise ValueError(f'equipment model not found: {actor}')
    return {name:available[name] for name in names}


def library_counts(path, expected_actors):
    data=path.read_bytes()
    if len(data)<17 or data[:4]!=b'LNKA':
        raise ValueError('gear conversion did not produce an LNKA library')
    version, models, actors=struct.unpack_from('<III',data,4)
    if version!=2 or models<1 or models>expected_actors or actors!=expected_actors or data[16]!=0:
        raise ValueError('gear library has missing or unexpected entries')
    at=17
    for _ in range(actors):
        if at+54>len(data): raise ValueError('truncated equipment actor record')
        model,=struct.unpack_from('<i',data,at+48)
        # This selective converter emits neither armor hides nor material groups.
        if model<0 or model>=models or data[at+52]!=0 or data[at+53]!=0:
            raise ValueError('equipment actor has no converted model')
        at+=54
    for _ in range(models):
        if at+70>len(data): raise ValueError('truncated equipment model header')
        nv,nt,side,nastc,zsize=struct.unpack_from('<5I',data,at+48)
        nmats,=struct.unpack_from('<H',data,at+68)
        if not nv or not nt or nv>1000000 or nt>1000000 or not 8<=side<=512 or nastc>4096 or nmats>1024 or not zsize:
            raise ValueError('invalid equipment model bounds')
        at+=70
        for _ in range(nmats):
            if at>=len(data) or at+1+data[at]>len(data): raise ValueError('truncated material name')
            at+=1+data[at]
        size=28*nv+39*nt+zsize
        if at+size>len(data): raise ValueError('truncated equipment geometry or atlas')
        triangles=at+28*nv
        for i in range(3*nt):
            if struct.unpack_from('<I',data,triangles+4*i)[0]>=nv: raise ValueError('invalid equipment vertex index')
        at+=size
        for _ in range(nastc):
            if at+28>len(data): raise ValueError('truncated equipment ASTC header')
            x,y,w,h,bw,bh,blockbytes=struct.unpack_from('<7I',data,at); bw&=255
            if not w or not h or x+w>side or y+h>side or not 4<=bw<=12 or not 4<=bh<=12 or \
                ((w+bw-1)//bw)*((h+bh-1)//bh)*16>blockbytes or at+28+blockbytes>len(data):
                raise ValueError('invalid equipment ASTC bounds')
            at+=28+blockbytes
    if at!=len(data): raise ValueError('unexpected equipment library trailer')
    return models, actors


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--romfs',required=True,type=Path)
    ap.add_argument('--mcsharp',required=True,type=Path)
    ap.add_argument('--actor',action='append',required=True,help='equipped base actor; repeat for at most sixteen items')
    ap.add_argument('--out',type=private_output,default=ROOT/'build/coop-v143/assets/link-gear.bin')
    ap.add_argument('--work',type=private_output,default=ROOT/'build/coop-v143/gear-work')
    args=ap.parse_args()
    if sys.version_info<(3,14): ap.error('use Python3.14 for compression.zstd')
    import link_figure
    out, work=private_output(args.out),private_output(args.work)
    decoder=args.mcsharp.resolve()
    if not decoder.is_file(): ap.error('McSharp executable is missing')
    if shutil.disk_usage(ROOT).free<25*1024**3: ap.error('keep at least25GiB free before preparing assets')
    out.parent.mkdir(parents=True,exist_ok=True); work.mkdir(parents=True,exist_ok=True)
    romfs=link_figure.RomFS(args.romfs)
    try:
        chosen=select_actors(args.actor,link_figure.weapon_actors(romfs,link_figure.zstd_dicts(romfs)))
        # Immutable decoder inputs and outputs remain isolated below ignored build/.
        for model in sorted(set(chosen.values())):
            data=romfs.read(f'Model/{model}.bfres.mc')
            if data is None: raise FileNotFoundError(f'{model} is missing from RomFS')
            (work/f'{model}.bfres.mc').write_bytes(data)
        run=subprocess.run([str(decoder),str(work),str(work)],capture_output=True,text=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=120)
        if run.returncode: raise RuntimeError(f'McSharp failed: {run.stdout[-800:]} {run.stderr[-800:]}')
        temporary=out.with_suffix('.tmp')
        try:
            link_figure.build_armor(work,romfs,None,chosen,temporary,include_body=False)
            models, actors=library_counts(temporary,len(chosen))
            with temporary.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
            info=dict(marker=GENERATED_MARKER,upstream_revision='7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c',
                      format='LNKA',version=2,models=models,actors=chosen,bytes=temporary.stat().st_size,sha256=digest,
                      native_placement_verified=False,inventory_replication=False)
            manifest=out.with_suffix('.json'); manifest_tmp=manifest.with_suffix('.json.tmp')
            manifest_tmp.write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
            os.replace(temporary,out); os.replace(manifest_tmp,manifest)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        romfs.rom.close()
    print(f'Prepared {models} models for {actors} equipped actors: {out}')
    print('Attachment capture/rendering is a separate implementation gate.')


if __name__=='__main__': main()
