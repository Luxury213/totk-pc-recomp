"""Exercise the production figure loader, animation and snapshot bridge using an authored triangle, not game data."""
import os
import argparse
import re
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include "link_figure.c"
#include "coop_figure.c"
static uint8_t *bytes;
static uint64_t size, clock_ms=1000;
static GfxFigure sent;
static int count;
const RtConfig *rt_config(void) { static RtConfig cfg={.profile="synthetic"}; return &cfg; }
void rt_log(const char *fmt,...) { (void)fmt; }
void plat_mutex_lock(PlatMutex *lock) { (void)lock; }
void plat_mutex_unlock(PlatMutex *lock) { (void)lock; }
uint64_t plat_now_ns(void) { return clock_ms * 1000000; }
int64_t plat_file_size(const char *path) { (void)path; return (int64_t)size; }
uint8_t *plat_file_read(const char *path,uint64_t *n) {
    (void)path; *n=size; uint8_t *p=malloc(size); memcpy(p,bytes,size); return p;
}
void astc_decode_ldr(const uint8_t *blocks,uint32_t w,uint32_t h,uint32_t bw,uint32_t bh,bool srgb,uint8_t *out) {
    (void)blocks;(void)w;(void)h;(void)bw;(void)bh;(void)srgb;(void)out; assert(0);
}
int gfx_figures_wanted(void) { return link_figure()!=NULL; }
void gfx_figures_set(const GfxFigure *figures,int n) { count=n; if(n) sent=figures[0]; }
int main(int argc,char **argv) {
    assert(argc==2); FILE *f=fopen(argv[1],"rb"); assert(f);
    fseek(f,0,SEEK_END); size=(uint64_t)ftell(f); rewind(f); bytes=malloc(size); assert(bytes);
    assert(fread(bytes,1,size,f)==size); fclose(f);
    // Every truncated prefix must reject cleanly, including partially allocated animation arrays.
    for(uint64_t n=0;n<size;n++) { assert(!parse(bytes,n)); figure_clear(); }
    uint8_t *bad=malloc(size); assert(bad);
    memcpy(bad,bytes,size); memset(bad+60,0xff,4); assert(!parse(bad,size)); figure_clear(); // bad triangle index
    memcpy(bad,bytes,size); memset(bad+353,0xff,4); assert(!parse(bad,size)); figure_clear(); // excessive bone count
    memcpy(bad,bytes,size); memset(bad+413,0,4); assert(!parse(bad,size)); figure_clear(); // cyclic parent
    uint8_t *overflow=calloc(1,size+44); assert(overflow);
    memcpy(overflow,bytes,353); overflow[20]=1;
    uint32_t rect[7]={UINT32_MAX,0,2,2,4,4,16}; memcpy(overflow+353,rect,sizeof rect);
    memcpy(overflow+397,bytes+353,size-353);
    assert(!parse(overflow,size+44)); figure_clear(); free(overflow); // rectangle addition must not wrap
    free(bad);
    const LinkFigure *model=link_figure(); assert(model && model->nverts==3 && model->ntris==1);
    assert(model->nbones==1 && model->nanims==1 && link_figure_find(model,"Synthetic_Move")==0);
    float pose[9]; link_figure_pose(model,0,15,pose);
    assert(fabsf(pose[0]-1)<.001f && fabsf(pose[3]-2)<.001f && pose[7]==1);
    link_figure_pose(model,0,30,pose); assert(fabsf(pose[0])<.001f); // loop wrap
    CoopSnapshot snapshot={.has_peer_pos=1,.has_local_pos=1,.peer_pos={10,20,30},
        .peer_visual_flags=COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION,
        .peer_rotation={0,.70710678f,0,.70710678f},.peer_animation="Synthetic_Move",.peer_animation_frame=15};
    coop_figure_publish(&snapshot); assert(count==1 && sent.frame==15 && sent.feet[0]==10);
    assert(fabsf(sent.rot[2]-1)<.001f && fabsf(sent.rot[6]+1)<.001f);
    snapshot.has_peer_pos=0; coop_figure_publish(&snapshot); assert(count==0);
    snapshot.has_peer_pos=1; snapshot.peer_visual_flags=0;
    coop_figure_publish(&snapshot); float before=sent.frame;
    clock_ms+=100; coop_figure_publish(&snapshot); assert(sent.frame>before); // idle clock advances
    figure_clear(); free(bytes);
    puts("co-op figure: truncated assets, invalid indices, curves, loop wrap, orientation and disappearance passed");
    return 0;
}
'''


def fixture():
    data = bytearray(b'LNKF') + struct.pack('<5I', 4, 3, 1, 8, 0)
    data += struct.pack('<9f3I', 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    data += bytes([128]) + struct.pack('<6f', 0, 0, 1, 0, 0, 1) + bytes([255])*256
    data += struct.pack('<2I', 1, 1) + struct.pack('<8H', 0, 65535, 0, 0, 0, 0, 0, 0)*3
    data += struct.pack('<I', 0xffffffff)
    bind = (1, 1, 1, 0, 0, 0, 0, 0, 0)
    data += struct.pack('<i9f12f', -1, *bind, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0)
    data += b'Root'.ljust(32, b'\0')
    data += b'Synthetic_Move'.ljust(48, b'\0') + struct.pack('<IIfIII', 30, 1, 1, 1, 1, 2)
    data += struct.pack('<HH9f', 0, 1, *bind) + struct.pack('<BBH', 6, 0, 2)
    data += struct.pack('<H4eH4e', 0, 0, 2, 0, 0, 960, 2, 0, 0, 0)
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', default='C:/msys64/ucrt64/bin/clang.exe')
    ap.add_argument('--deps', type=Path)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / 'tools'))
    from prepare_coop_figure import private_output
    from build_coop import install_figure
    from unittest.mock import patch
    assert private_output(ROOT / 'build/tests/figure.bin').is_relative_to(ROOT / 'build')
    for path in (ROOT / 'runtime/figure.bin', ROOT / 'build', ROOT / 'build/../figure.bin'):
        try:
            private_output(path)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f'accepted public asset output: {path}')
    # Every command must enter the async recorder. Direct commands race its VkCommandPool.
    commands = set(re.findall(r'\b(vkCmd\w+)\s*\(', (ROOT / 'runtime/vk_figure.c').read_text()))
    recorded = set(re.findall(r'^#define (vkCmd\w+) ', (ROOT / 'runtime/vk_rec.h').read_text(), re.M))
    assert commands <= recorded, f'figure bypasses async recording: {commands - recorded}'
    output = ROOT / 'build/tests'
    output.mkdir(parents=True, exist_ok=True)
    compiler = args.cc
    deps = args.deps or Path(compiler).parent.parent / 'include'
    env = dict(os.environ, PATH=str(Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
    with tempfile.TemporaryDirectory(prefix='coop-figure-', dir=output) as folder:
        work = Path(folder)
        source = work / 'assets/link-figure.bin'
        target = work / 'profile/link-figure.bin'
        source.parent.mkdir()
        source.write_bytes(b'authored immutable fixture')
        install_figure(source, target)
        install_figure(source, target)  # idempotent even when both names already share storage
        assert target.read_bytes() == source.read_bytes()
        replacement = source.with_suffix('.new')
        replacement.write_bytes(b'new authored fixture')
        shared = os.path.samefile(source, target)
        replacement.replace(source)
        if shared:
            assert target.read_bytes() == b'authored immutable fixture'  # old snapshot remains intact
        with patch('build_coop.os.link', side_effect=OSError('unsupported filesystem')):
            install_figure(source, target)
        assert target.read_bytes() == b'new authored fixture'
        assert source.read_bytes() == b'new authored fixture' and not os.path.samefile(source, target)
        assert not list(target.parent.glob('.*.tmp'))
        try:
            install_figure(source, work / 'save.dat')
        except ValueError:
            pass
        else:
            raise AssertionError('accepted a writable non-figure destination')
        (work / 'check.c').write_text(HARNESS, encoding='utf-8')
        (work / 'triangle.bin').write_bytes(fixture())
        subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'runtime'), '-I', str(deps), '-I', str(deps / 'vma'),
                        str(work / 'check.c'), '-o', str(work / 'check.exe')], check=True, env=env)
        subprocess.run([str(work / 'check.exe'), str(work / 'triangle.bin')], check=True, env=env)


if __name__ == '__main__':
    main()
