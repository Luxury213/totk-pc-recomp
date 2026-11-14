"""Build the game-free loopback ENet peer used by the isolated native velocity diagnostic."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build_peer(cc='C:/msys64/ucrt64/bin/clang.exe'):
    out = ROOT / 'build/tools/coop-velocity-peer.exe'
    out.parent.mkdir(parents=True, exist_ok=True)
    enet = ROOT / 'runtime/third_party/enet'
    sources = [ROOT / 'tools/coop_velocity_peer.c'] + [ROOT / 'runtime' / name for name in
               ('coop_net.c', 'coop_wire.c', 'coop_session.c', 'platform/win32.c', 'platform/common.c')]
    sources += [enet / name for name in ('callbacks.c', 'compress.c', 'host.c', 'list.c', 'packet.c',
                                       'peer.c', 'protocol.c', 'win32.c')]
    if out.is_file() and all(p.stat().st_mtime <= out.stat().st_mtime for p in
                            [*sources, *enet.glob('include/enet/*.h'), *ROOT.glob('runtime/coop_*.h'), Path(__file__)]):
        return out
    env = dict(os.environ, PATH=str(Path(cc).parent) + os.pathsep + os.environ.get('PATH', ''))
    subprocess.run([cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-flto', '-ffunction-sections',
                    '-fdata-sections', '-fuse-ld=lld', '-Wl,--gc-sections', '-Wl,--exclude-all-symbols',
                    '-D_WIN32_WINNT=0x0A00', '-I', str(ROOT / 'runtime'), '-I', str(enet / 'include'),
                    *map(str, sources), '-lws2_32', '-lwinmm', '-lbcrypt', '-o', str(out)], check=True, env=env)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='C:/msys64/ucrt64/bin/clang.exe')
    print(build_peer(parser.parse_args().cc))
