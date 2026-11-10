"""Build/run the co-op protocol and real two-worker ENet checks, without game data (Windows first)."""
import argparse
import heapq
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import random

ROOT = Path(__file__).resolve().parents[1]


class ImpairedLink:
    """A deterministic UDP proxy; impair ENet datagrams, not application messages or the state machine."""
    def __init__(self, destination, rtt_ms):
        self.destination = ('127.0.0.1', destination)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        if hasattr(socket, 'SIO_UDP_CONNRESET'):
            self.sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(.002)
        self.stop = threading.Event()
        self.rtt_ms = rtt_ms
        self.counts = dict(received=0, dropped=0, duplicated=0, delayed_for_reordering=0)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        rng = random.Random(143 + self.rtt_ms)
        pending, client, sequence = [], None, 0
        while not self.stop.is_set():
            now = time.monotonic()
            while pending and pending[0][0] <= now:
                _, _, data, target = heapq.heappop(pending)
                try:
                    self.sock.sendto(data, target)
                except ConnectionResetError:
                    pass   # delayed datagrams can address a client socket closed during the reconnect test
            try:
                data, sender = self.sock.recvfrom(65535)
            except (socket.timeout, ConnectionResetError):
                continue
            self.counts['received'] += 1
            if sender == self.destination:
                target = client
            else:
                client, target = sender, self.destination
            if not target:
                continue
            if rng.random() < .05:
                self.counts['dropped'] += 1
                continue
            delay = max(0, self.rtt_ms / 2000 + rng.uniform(-.020, .020))
            if rng.random() < .10:
                delay += .060
                self.counts['delayed_for_reordering'] += 1
            sequence += 1
            heapq.heappush(pending, (now + delay, sequence, data, target))
            if rng.random() < .02:
                self.counts['duplicated'] += 1
                sequence += 1
                heapq.heappush(pending, (now + delay + .010, sequence, data, target))

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.sock.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', default='C:/msys64/ucrt64/bin/clang.exe')
    args = ap.parse_args()
    if os.name != 'nt':
        ap.error('the real worker test currently links the Windows platform implementation')
    output = ROOT / 'build' / 'tests'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(Path(args.cc).parent) + os.pathsep + os.environ.get('PATH', ''))
    with tempfile.TemporaryDirectory(prefix='coop-network-', dir=output) as tmp:
        folder = Path(tmp)
        common = [args.cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'runtime')]
        protocol = [str(ROOT / 'runtime' / name) for name in ('coop_wire.c', 'coop_session.c', 'coop_interp.c')]
        exe = folder / 'protocol.exe'
        subprocess.run([*common, str(ROOT / 'tests' / 'coop_session_check.c'), *protocol, '-o', str(exe)],
                       check=True, env=env)
        subprocess.run([str(exe)], check=True, env=env, timeout=20)
        enet = ROOT / 'runtime' / 'third_party' / 'enet'
        sources = [str(enet / name) for name in ('callbacks.c', 'compress.c', 'host.c', 'list.c', 'packet.c',
                                                'peer.c', 'protocol.c', 'win32.c')]
        exe = folder / 'network.exe'
        # Third-party code keeps upstream warnings; -Werror applies to the separately tested project protocol.
        subprocess.run([*common, '-Wno-error', '-flto', '-ffunction-sections', '-fdata-sections', '-fuse-ld=lld',
                        '-Wl,--gc-sections', '-Wl,--exclude-all-symbols', '-D_WIN32_WINNT=0x0A00',
                        '-I', str(enet / 'include'), str(ROOT / 'tests' / 'coop_network_check.c'),
                        *protocol, str(ROOT / 'runtime' / 'coop_net.c'),
                        str(ROOT / 'runtime' / 'platform' / 'win32.c'),
                        str(ROOT / 'runtime' / 'platform' / 'common.c'), *sources,
                        '-lws2_32', '-lwinmm', '-lbcrypt', '-o', str(exe)], check=True, env=env)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        report = []
        for rtt_ms in (0, 100, 200):
            proxy = ImpairedLink(port, rtt_ms) if rtt_ms else None
            try:
                command = [str(exe), str(port), str(folder / f'profile-{rtt_ms}')]
                if proxy:
                    command.append(str(proxy.port))
                subprocess.run(command, check=True, env=env, timeout=55)
                row = dict(rtt_ms=rtt_ms, passed=True, **(proxy.counts if proxy else {}))
                report.append(row)
                print('ENet impairment scenario:', row, flush=True)
            finally:
                if proxy:
                    proxy.close()
        (output / 'coop-network-results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
