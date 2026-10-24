#!/usr/bin/env python3
"""Opt-in bounded PTY smoke test on an operator-owned disposable destination."""
import argparse
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
                            timeout=5, check=True, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    return result.stdout.decode().strip()


def drive(argv, output, timeout, env):
    saved = termios.tcgetattr(0)
    size = fcntl.ioctl(0, termios.TIOCGWINSZ, b'\0' * 8)
    events = []
    previous = {signal.SIGALRM: signal.getsignal(signal.SIGALRM)}
    pid, master = pty.fork()
    if pid == 0:
        try:
            os.execve(argv[0], argv, env)
        except OSError:
            os._exit(126)
    status, outcome, count = None, 'exited', 0
    deadline = time.monotonic() + timeout
    expired = False

    def resize(_signum, _frame):
        current = fcntl.ioctl(0, termios.TIOCGWINSZ, b'\0' * 8)
        fcntl.ioctl(master, termios.TIOCSWINSZ, current)
        rows, columns, _, _ = struct.unpack('HHHH', current)
        if len(events) < 256:
            events.append({'event': 'resize', 'rows': rows, 'columns': columns, 'at': now()})

    def cancel(_signum, _frame):
        raise KeyboardInterrupt

    def expire(_signum, _frame):
        nonlocal expired
        if not expired:
            expired = True
            raise TimeoutError

    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, size)
        for signum, handler in ((signal.SIGWINCH, resize), (signal.SIGTERM, cancel), (signal.SIGHUP, cancel), (signal.SIGALRM, expire)):
            previous[signum] = signal.signal(signum, handler)
        tty.setraw(0)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        with (output / 'terminal.log').open('xb') as transcript:
            while True:
                if time.monotonic() >= deadline:
                    outcome = 'timeout'
                    break
                ready, _, _ = select.select([0, master], [], [], min(0.1, max(0, deadline - time.monotonic())))
                if master in ready:
                    try:
                        data = os.read(master, 8192)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        data = b''
                    if not data:
                        break
                    if count + len(data) > LIMIT:
                        outcome = 'output-limit'
                        break
                    transcript.write(data)
                    count += len(data)
                    os.write(1, data)
                if 0 in ready:
                    data = os.read(0, 1024)
                    if not data:
                        outcome = 'cancelled'
                        break
                    os.write(master, data)
    except TimeoutError:
        outcome = 'timeout'
    except KeyboardInterrupt:
        outcome = 'cancelled'
    except (OSError, termios.error):
        outcome = 'io-error'
    finally:
        try:
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
        except TimeoutError:
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            termios.tcsetattr(0, termios.TCSANOW, saved)
        except (OSError, termios.error):
            outcome = 'io-error'
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        os.close(master)
        if status is None:
            grace = time.monotonic() + 0.2
            while time.monotonic() < grace:
                waited, raw = os.waitpid(pid, os.WNOHANG)
                if waited:
                    status = raw
                    break
                select.select([], [], [], 0.01)
        if status is None:
            waited, raw = os.waitpid(pid, os.WNOHANG)
            if waited:
                status = raw
            else:
                if outcome == 'exited':
                    outcome = 'cancelled'
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                end = time.monotonic() + 1
                while time.monotonic() < end:
                    waited, raw = os.waitpid(pid, os.WNOHANG)
                    if waited:
                        status = raw
                        break
                    select.select([], [], [], 0.02)
                if status is None:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status = os.waitpid(pid, 0)
    return {'outcome': outcome, 'exit_code': os.waitstatus_to_exitcode(status),
            'wait_status': status, 'events': events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--platform', required=True, choices=('linux', 'macos'))
    parser.add_argument('--consent', required=True, choices=('disposable-pty-smoke',))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    try:
        if not re.fullmatch('[0-9a-f]{40}', args.expected_commit):
            raise ValueError('full expected commit required')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:_-]{0,252}', args.target):
            raise ValueError('invalid target')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}', args.user) or args.user == 'root':
            raise ValueError('explicit nonroot test user required')
        if not 1 <= args.timeout <= 180:
            raise ValueError('timeout must be between 1 and 180 seconds')
        if platform.system() != {'linux': 'Linux', 'macos': 'Darwin'}[args.platform]:
            raise ValueError('client platform mismatch')
        if git('rev-parse', 'HEAD') != args.expected_commit:
            raise ValueError('checkout does not match expected commit')
        if git('status', '--porcelain', '--untracked-files=normal'):
            raise ValueError('reviewed checkout must be clean, including untracked files')
        if not all(os.isatty(fd) for fd in (0, 1)):
            raise ValueError('actual interactive terminal required')
        output = args.output.absolute()
        if ROOT == output or ROOT in output.parents:
            raise ValueError('private output must be outside the checkout')
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError('symlink output refused')
        os.umask(0o077)
        output.mkdir(mode=0o700)
        argv = ['/bin/bash', str(ROOT / 'bin/tailmux'), args.user + '@' + args.target]
        started = now()
        env = {key: os.environ[key] for key in ('HOME', 'PATH', 'TERM', 'SSH_AUTH_SOCK') if key in os.environ}
        env['LC_ALL'] = 'C'
        result = drive(argv, output, args.timeout, env)
        transcript = output / 'terminal.log'
        result.update({'schema': 1, 'source_sha': args.expected_commit, 'platform': args.platform,
                       'argv': argv, 'scope': args.consent, 'started_at': started, 'finished_at': now(),
                       'terminal_log_sha256': hashlib.sha256(transcript.read_bytes()).hexdigest(),
                       'native_recording': 'UNAVAILABLE', 'verdict': 'NOT_VERIFIED',
                       'redaction': 'PRIVATE_UNREVIEWED',
                       'cleanup': 'local child reaped; operator must inspect remote sessions'})
        (output / 'smoke.json').write_text(json.dumps(result, indent=2) + '\n')
        print('\r\nPrivate smoke receipt saved. NOT VERIFIED. Review and redact before sharing.')
        return {'timeout': 124, 'cancelled': 130, 'output-limit': 125, 'io-error': 74}.get(
            result['outcome'], result['exit_code'] if result['exit_code'] >= 0 else 128 - result['exit_code'])
    except (ValueError, OSError, termios.error, subprocess.SubprocessError):
        print('smoke refused: check expected commit, clean checkout, target, user, platform, terminal, and private output', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
