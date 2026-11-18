"""Build/run the co-op protocol and real two-worker ENet checks, without game data (Windows first)."""
import argparse
import heapq
import json
import os
from pathlib import Path
import socket
import selectors
import subprocess
import tempfile
import threading
import time
import random

ROOT = Path(__file__).resolve().parents[1]


class ImpairedLink:
    """A deterministic UDP proxy; impair ENet datagrams, not application messages or the state machine."""
    def __init__(self, destination, rtt_ms, *, drop_first_disconnect=False, impair=True):
        self.destination = ('127.0.0.1', destination)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        if hasattr(socket, 'SIO_UDP_CONNRESET'):
            self.sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        self.port = self.sock.getsockname()[1]
        self.sock.setblocking(False)
        self.stop = threading.Event()
        self.rtt_ms = rtt_ms
        self.drop_first_disconnect = drop_first_disconnect
        self.impair = impair
        self.counts = dict(received=0, dropped=0, duplicated=0, delayed_for_reordering=0,
                           forced_disconnect_drops=0)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        rng = random.Random(143 + self.rtt_ms)
        pending, clients, sequence = [], {}, 0
        # Distinct client UDP endpoints need distinct server-facing sockets. Reusing one upstream port
        # made a delayed response for an old connection reach whichever client sent most recently.
        with selectors.DefaultSelector() as watch:
            watch.register(self.sock, selectors.EVENT_READ, None)
            try:
                while not self.stop.is_set():
                    now = time.monotonic()
                    while pending and pending[0][0] <= now:
                        _, _, data, outbound, target = heapq.heappop(pending)
                        try:
                            outbound.sendto(data, target)
                        except ConnectionResetError:
                            pass  # delayed packets can address an endpoint closed during reconnect
                    for key, _ in watch.select(.002):
                        try:
                            data, sender = key.fileobj.recvfrom(65535)
                        except (BlockingIOError, ConnectionResetError):
                            continue
                        to_server = key.data is None
                        if to_server:
                            if sender not in clients:
                                upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                upstream.bind(('127.0.0.1', 0))
                                upstream.setblocking(False)
                                if hasattr(socket, 'SIO_UDP_CONNRESET'):
                                    upstream.ioctl(socket.SIO_UDP_CONNRESET, False)
                                clients[sender] = upstream
                                watch.register(upstream, selectors.EVENT_READ, sender)
                            outbound, target = clients[sender], self.destination
                        else:
                            if sender != self.destination:
                                continue
                            outbound, target = self.sock, key.data
                        self.counts['received'] += 1
                        # Fixtures disable checksum/compression. Disconnect resets preceding commands,
                        # leaving its command header immediately after the 2/4-byte datagram header.
                        header = 4 if len(data)>=2 and int.from_bytes(data[:2], 'big') & 0x8000 else 2
                        if (self.drop_first_disconnect and not to_server and
                                len(data) >= header+8 and data[header] & 15 == 4):
                            self.drop_first_disconnect = False
                            self.counts['forced_disconnect_drops'] += 1
                            continue
                        if self.impair and rng.random() < .05:
                            self.counts['dropped'] += 1
                            continue
                        now = time.monotonic()
                        delay = max(0, self.rtt_ms / 2000 + (rng.uniform(-.020, .020) if self.impair else 0))
                        if self.impair and rng.random() < .10:
                            delay += .060
                            self.counts['delayed_for_reordering'] += 1
                        sequence += 1
                        heapq.heappush(pending, (now + delay, sequence, data, outbound, target))
                        if self.impair and rng.random() < .02:
                            self.counts['duplicated'] += 1
                            sequence += 1
                            heapq.heappush(pending, (now + delay + .010, sequence, data, outbound, target))
            finally:
                for upstream in clients.values():
                    upstream.close()

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
        protocol = [str(ROOT / 'runtime' / name) for name in ('coop_body.c', 'coop_equipment.c', 'coop_wire.c', 'coop_session.c', 'coop_interp.c')]
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
        scenarios = [(0, None), (100, None), (200, None), (100, 'reject-loss'), (100, 'reject-protocol-loss')]
        for rtt_ms, reject_loss in scenarios:
            proxy = ImpairedLink(port, rtt_ms, drop_first_disconnect=reject_loss,
                                 impair=not reject_loss) if rtt_ms else None
            row = dict(rtt_ms=rtt_ms, scenario=reject_loss or 'movement', passed=False)
            try:
                command = [str(exe), str(port), str(folder / f'profile-{rtt_ms}-{reject_loss}')]
                if proxy:
                    command.append(str(proxy.port))
                if reject_loss:
                    command.append(reject_loss)
                subprocess.run(command, check=True, env=env, timeout=55)
                if reject_loss:
                    assert proxy.counts['forced_disconnect_drops'] == 1
                row['passed'] = True
            finally:
                if proxy:
                    proxy.close()
                    row.update(proxy.counts)
                report.append(row)
                (output / 'coop-network-results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                print('ENet impairment scenario:', row, flush=True)


if __name__ == '__main__':
    main()
