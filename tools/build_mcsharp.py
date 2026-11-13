"""Build the pinned MIT MeshCodec decoder for local co-op figure preparation.

Run tools/fetch_refs.sh first, then use .venv/Scripts/python.exe tools/build_mcsharp.py.
Pass --dotnet when the SDK is not on PATH or under toolchain/dotnet/. No game inputs are read.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'c837ee41217fd5b330ea31cc21448cf4985320f8'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dotnet', type=Path)
    args = ap.parse_args()
    reference = ROOT / 'refs/McSharp'
    revision = subprocess.run(['git', '-C', str(reference), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
    if revision != REVISION:
        ap.error(f'refs/McSharp must be at {REVISION}; run tools/fetch_refs.sh')
    dotnet = args.dotnet or shutil.which('dotnet')
    portable = ROOT / 'toolchain/dotnet/dotnet.exe'
    if args.dotnet is None and portable.is_file():
        dotnet = portable
    if not dotnet:
        ap.error('a .NET SDK is required; pass --dotnet <path to dotnet>')
    work = ROOT / 'build/tools/mcsharp' / REVISION
    source, output = work / 'source', work / 'bin'
    source.mkdir(parents=True, exist_ok=True)
    # Build a copy: MSBuild must never emit obj/bin files into the read-only reference.
    shutil.copytree(reference / 'src', source / 'src', dirs_exist_ok=True)
    for name in ('LICENSE', 'README.md'):
        shutil.copy2(reference / name, source / name)
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
               DOTNET_GENERATE_ASPNET_CERTIFICATE='false',
               NUGET_PACKAGES=str(work / 'packages'))
    command = [str(dotnet), 'publish', str(source / 'src/McSharp.Cli/McSharp.Cli.csproj'),
               '-c', 'Release', '-r', 'win-x64', '--self-contained', 'true',
               '--artifacts-path', str(work / 'artifacts'), '-o', str(output)]
    subprocess.run(command, check=True, env=env)
    shutil.copy2(reference / 'LICENSE', output / 'McSharp-LICENSE.txt')
    shutil.copy2(ROOT / 'runtime/third_party/licenses/ZstdSharp.txt', output / 'ZstdSharp-LICENSE.txt')
    print(output / 'mcsharp-cli.exe')


if __name__ == '__main__':
    main()
