import argparse
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def _detect_venv_python() -> Path:
    """Return the Python executable for the active virtual environment."""
    return BASE / '.venv' / 'Scripts' / 'python.exe'

VENV_PYTHON = _detect_venv_python()

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--quiet', action='store_true')
args, unknown = parser.parse_known_args()
QUIET = args.quiet
sys.argv = [sys.argv[0]] + unknown


def notify(message: str, error: bool = False) -> None:
    """Print helper that respects quiet mode except for errors."""
    if not QUIET or error:
        print(message)

def silent_notify(message: str) -> None:
    """Print only in non-quiet mode, completely silent in quiet mode."""
    if not QUIET:
        print(message)


if not VENV_PYTHON.exists():
    notify(
        'Virtual environment not found (.venv). '
        'Please create it with "python -m venv .venv".',
        error=True
    )
    sys.exit(1)

SITE_PACKAGES = Path(VENV_PYTHON).parent.parent / 'Lib' / 'site-packages'
if not SITE_PACKAGES.exists():
    notify(f'Site-packages directory not found: {SITE_PACKAGES}', error=True)
    sys.exit(1)

TARGET_VERSIONS = {
    'pip': '25.2',
    'setuptools': '80.9.0',
    'wheel': '0.45.1',
}


def run(cmd: list[str]) -> None:
    effective_cmd = cmd[:]
    if QUIET:
        def _insert_flag(flag: str, anchor: str) -> None:
            if flag in effective_cmd or '-q' in effective_cmd:
                return
            try:
                idx = effective_cmd.index(anchor)
            except ValueError:
                return
            effective_cmd.insert(idx + 1, flag)

        _insert_flag('--quiet', 'pip')
        _insert_flag('--quiet', 'ensurepip')

    if QUIET:
        result = subprocess.run(
            effective_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        output = result.stdout or ""
    else:
        result = subprocess.run(effective_cmd)
        output = ""

    if result.returncode != 0:
        if QUIET and output:
            notify(output, error=True)
        notify('Command failed: ' + ' '.join(effective_cmd), error=True)
        sys.exit(result.returncode)


def remove_patterns(*patterns: str) -> None:
    for pattern in patterns:
        for target in SITE_PACKAGES.glob(pattern):
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass


def get_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def version_tuple(version: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r'\d+', version)]
    return tuple(parts) if parts else (0,)


def needs_upgrade(package: str, minimum: str) -> bool:
    installed = get_version(package)
    if installed is None:
        return True
    return version_tuple(installed) < version_tuple(minimum)


def check_requirements_file(requirements_path: Path) -> bool:
    """Check if any packages from requirements.txt need installation."""
    if not requirements_path.exists():
        return False

    with open(requirements_path, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue

        # Parse package name and version
        package_spec = line.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].strip()

        # Check if package is installed
        if get_version(package_spec) is None:
            return True

    return False


# Check what needs to be done
pip_missing = get_version('pip') is None
packages_to_upgrade = [
    name for name, minimum in TARGET_VERSIONS.items()
    if needs_upgrade(name, minimum)
]

# Determine if any work is needed (for showing message)
needs_work = pip_missing or packages_to_upgrade

# Only show message if actually installing
if needs_work and QUIET:
    print('Installing dependencies...')

# Bootstrap pip if needed
if pip_missing:
    silent_notify('Bootstrapping pip (not found in environment)...')
    remove_patterns('pip', 'pip-*', 'setuptools', 'setuptools-*', 'wheel', 'wheel-*', 'pip_vendor', 'pip_vendor-*')
    run([str(VENV_PYTHON), '-m', 'ensurepip', '--upgrade', '--default-pip'])

# Upgrade packaging tools if needed
if packages_to_upgrade:
    silent_notify(f'Upgrading packaging tools ({", ".join(packages_to_upgrade)})...')
    run([
        str(VENV_PYTHON), '-m', 'pip', 'install',
        '--upgrade', '--disable-pip-version-check', *packages_to_upgrade
    ])

# Clean up old whisper backend if migrating to faster-whisper
if get_version('openai-whisper') is not None and get_version('faster-whisper') is None:
    silent_notify('Migrating from openai-whisper to faster-whisper...')
    # Uninstall openai-whisper and its heavy deps that faster-whisper doesn't need
    run([str(VENV_PYTHON), '-m', 'pip', 'uninstall', '-y', 'openai-whisper', '--disable-pip-version-check'])

# Always install requirements.txt (pip handles already-satisfied packages silently)
silent_notify('Installing project requirements...')
run([str(VENV_PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(BASE / 'requirements.txt')])

if needs_work:
    silent_notify('Dependencies installed successfully.')
