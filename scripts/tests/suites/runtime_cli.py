#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from fixture_env import cli_environment

ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / 'bin/tailmux'
FIXTURE = ROOT / 'scripts/tests/fixtures/status-v1.104.2/running.json'
SENTRY_DSN = 'https://0123456789abcdef0123456789abcdef@o123.ingest.de.sentry.io/456'
REMOTE = 'if command -v tmux >/dev/null 2>&1; then tmux attach || tmux new; else printf "%s\\n" "tmux not found on remote" >&2; exit 127; fi'


class Runtime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tailmux-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'
        self.bin = self.root / 'bin'
        self.home.mkdir()
        self.bin.mkdir()
        for name in ('bash', 'jq', 'mktemp', 'head', 'wc', 'tr', 'rm', 'rmdir', 'cat'):
            command = shutil.which(name)
            self.assertIsNotNone(command, name)
            (self.bin / name).symlink_to(command)
        self.trace = self.root / 'trace'
        self.forbidden = self.root / 'forbidden'
        self.status = self.root / 'status.json'
        self.snapshot = json.loads(FIXTURE.read_text())
        self.write_status()
        self.env = {'HOME': str(self.home), 'ZDOTDIR': str(self.home), 'PATH': str(self.bin),
                    'SHELL': '/bin/bash', 'LC_ALL': 'C', 'TMPDIR': str(self.root),
                    'STATUS_FIXTURE': str(self.status), 'TRACE': str(self.trace),
                    'FORBIDDEN': str(self.forbidden)}
        self.script('tailscale', '''#!/bin/bash
printf '%s\\0' "$@" >> "$TRACE"
printf '\\n' >> "$TRACE"
socket=''
if [[ "${1:-}" == --socket=* ]]; then socket=${1#--socket=}; shift; fi
if [[ -n "${EXPECTED_SOCKET:-}" ]]; then
  if [[ "$socket" == "$EXPECTED_SOCKET" ]]; then
    STATUS_FIXTURE=$SELECTED_STATUS_FIXTURE
  elif [[ -n "$socket" ]]; then
    exit 37
  fi
fi
case "$1" in
  status) cat "$STATUS_FIXTURE"; exit "${STATUS_EXIT:-0}" ;;
  version) printf '%s\\n' '1.104.2 fixture'; exit 0 ;;
  ssh)
    if [[ -n "${EXEC_PID_FILE:-}" ]]; then
      printf '%s\\n' "$$" > "$EXEC_PID_FILE"
      exec /bin/sleep 30
    fi
    if [[ -n "${WRAPPER_ERROR:-}" ]]; then printf '%s\\n' "$WRAPPER_ERROR" >&2; fi
    exit "${WRAPPER_EXIT:-0}" ;;
esac
exit 97
''')
        self.script('ssh', '''#!/bin/bash
if [[ "$*" == -V ]]; then printf '%s\\n' OpenSSH_fixture; exit 0; fi
printf '%s\\n' "$0 $*" >> "$FORBIDDEN"
exit 97
''')
        for name in ('getent', 'dscacheutil', 'host', 'dig', 'nslookup', 'python', 'python3', 'sudo'):
            self.script(name, '#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$FORBIDDEN"\nexit 97\n')

    def script(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def write_status(self, raw=None):
        self.status.write_text(json.dumps(self.snapshot) if raw is None else raw)

    def run_client(self, *args, allow_missing_tailscale=False, **changes):
        return subprocess.run(['/bin/bash', str(CLIENT), *args], env=cli_environment(self.bin, self.env, allow_missing_tailscale=allow_missing_tailscale, **changes),
                              capture_output=True, text=True, timeout=10, cwd=self.root)

    def calls(self):
        if not self.trace.exists():
            return []
        return [line.split(b'\0')[:-1] for line in self.trace.read_bytes().split(b'\n') if line]

    def failure(self, code, *args, **changes):
        self.trace.unlink(missing_ok=True)
        p = self.run_client(*(args or ('work',)), **changes)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(code, p.stderr)
        self.assertIn(self.calls(), ([], [[b'status', b'--json']]))
        self.assertFalse(self.forbidden.exists())
        return p

    def test_success_exact_argv_and_doctor(self):
        p = self.run_client('Alice@WORK.Example.TS.Net.')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [[b'status', b'--json'],
                                      [b'ssh', b'Alice@100.64.0.20', b'-t', REMOTE.encode()]])
        self.trace.unlink()
        p = self.run_client('doctor', 'work')
        self.assertEqual(p.returncode, 0, p.stderr)
        target = json.loads(p.stdout)
        self.assertEqual(target['peerId'], 'nFixtureWork')
        self.assertEqual(target['canonicalDNS'], 'work.example.ts.net')
        self.assertIs(target['online'], False)
        self.assertIs(target['expired'], False)
        self.assertEqual(self.calls(), [[b'status', b'--json']])

    def test_selected_socket_resolves_and_executes_same_daemon(self):
        selected = self.root / 'selected.json'
        self.snapshot['Peer']['nodekey:fixture-a']['TailscaleIPs'] = ['100.64.0.88']
        selected.write_text(json.dumps(self.snapshot))
        self.snapshot['BackendState'] = 'Stopped'
        self.write_status()
        socket = str(self.root / "daemon space 'quote' \"double\" *?[x] ;$(touch marker)`id`.sock")
        changes = dict(EXPECTED_SOCKET=socket, SELECTED_STATUS_FIXTURE=str(selected))
        result = self.run_client('work', **changes)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stopped/not-ready', result.stderr)
        self.assertEqual(self.calls(), [[b'status', b'--json']])
        self.trace.unlink()
        result = self.run_client('doctor', 'work', TAILMUX_TAILSCALE_SOCKET=socket, **changes)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['address'], '100.64.0.88')
        self.assertEqual(self.calls(), [[f'--socket={socket}'.encode(), b'status', b'--json']])
        self.trace.unlink()
        result = self.run_client('Alice@work', TAILMUX_TAILSCALE_SOCKET=socket, **changes)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [[f'--socket={socket}'.encode(), b'status', b'--json'],
                                      [f'--socket={socket}'.encode(), b'ssh', b'Alice@100.64.0.88', b'-t', REMOTE.encode()]])
        self.assertFalse((self.root / 'marker').exists())
        self.assertFalse(self.forbidden.exists())

    def test_failed_explicit_socket_never_retries_working_default(self):
        socket = str(self.root / 'missing.sock')
        result = self.run_client('work', TAILMUX_TAILSCALE_SOCKET=socket,
                                 EXPECTED_SOCKET=str(self.root / 'working.sock'),
                                 SELECTED_STATUS_FIXTURE=str(self.status))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('daemon-unavailable', result.stderr)
        self.assertIn(socket, result.stderr)
        self.assertEqual(self.calls(), [[f'--socket={socket}'.encode(), b'status', b'--json']])

    def test_socket_configuration_is_validated_before_transport(self):
        for socket in ['', 'relative.sock'] + ['/tmp/control' + chr(c) for c in [*range(1, 32), 127]]:
            for args in [('work',), ('doctor',), ('doctor', 'work')]:
                with self.subTest(socket=repr(socket), args=args):
                    self.trace.unlink(missing_ok=True)
                    result = self.run_client(*args, TAILMUX_TAILSCALE_SOCKET=socket)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, 'tailmux: invalid-config: TAILMUX_TAILSCALE_SOCKET must be an absolute path without ASCII control bytes\n')
                    self.assertEqual(self.calls(), [])
        self.assertFalse(self.forbidden.exists())

    def test_selected_socket_backend_failures_retain_category_and_context(self):
        socket = str(self.root / 'selected.sock')
        for state, category in [('Stopped', 'stopped/not-ready'), ('NeedsLogin', 'logged-out')]:
            self.snapshot['BackendState'] = state
            self.write_status()
            self.trace.unlink(missing_ok=True)
            result = self.run_client('work', TAILMUX_TAILSCALE_SOCKET=socket)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(category, result.stderr)
            self.assertIn(socket, result.stderr)
            self.assertEqual(self.calls(), [[f'--socket={socket}'.encode(), b'status', b'--json']])

    def test_selected_socket_preserves_exec_pid_signals_exit_and_stderr(self):
        self.env['TAILMUX_TAILSCALE_SOCKET'] = str(self.root / 'selected.sock')
        self.test_wrapper_exit_error_and_exec_signal()
        self.assertTrue(all(call[0] == f"--socket={self.env['TAILMUX_TAILSCALE_SOCKET']}".encode()
                            for call in self.calls()))

    def test_address_shared_and_short_scoping(self):
        for selector, address in [('100.64.0.20', '100.64.0.20'),
                                  ('fd7a:115c:a1e0::2', 'fd7a:115c:a1e0::2'),
                                  ('shared.other.ts.net.', 'fd7a:115c:a1e0::3')]:
            with self.subTest(selector=selector):
                p = self.run_client('doctor', selector)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)['address'], address)
        for selector in ('shared', 'untrusted-reported-name', '100.64.0.99', '8.8.8.8', 'work.local', 'fd7a:115c:a1e0:0:0:0:0:2'):
            self.failure('unknown-selector', selector, TAILMUX_LAN_FALLBACK='1')
        for suffix in (None, {}, {'MagicDNSSuffix': ''}, {'MagicDNSSuffix': 'bad..suffix'}):
            self.snapshot['CurrentTailnet'] = suffix
            self.write_status()
            self.failure('unknown-selector', 'work')
            p = self.run_client('doctor', 'work.example.ts.net')
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_visible_collision_including_ineligible_and_all_addresses(self):
        base = copy.deepcopy(self.snapshot)
        for in_map, keys in [(True, ['ssh-ed25519 AAAA']), (False, []), (True, [])]:
            for field in ('DNSName', 'TailscaleIPs'):
                self.snapshot = copy.deepcopy(base)
                other = self.snapshot['Peer']['collision'] = copy.deepcopy(base['Peer']['nodekey:fixture-b'])
                other.update(ID='nCollision', InNetworkMap=in_map, sshHostKeys=keys)
                other[field] = base['Peer']['nodekey:fixture-a'][field]
                self.write_status()
                self.failure('ambiguous-selector', '100.64.0.20')
        self.snapshot = copy.deepcopy(base)
        other = self.snapshot['Peer']['collision'] = copy.deepcopy(base['Peer']['nodekey:fixture-b'])
        other.update(ID='nCollision', InNetworkMap=False, TailscaleIPs=['fd7a:115c:a1e0::2'])
        self.write_status()
        self.failure('ambiguous-selector', '100.64.0.20')

    def test_expired_keys_and_boolean_types(self):
        peer = self.snapshot['Peer']['nodekey:fixture-a']
        peer['Expired'] = True
        self.write_status()
        self.failure('peer-key-expired')
        peer.pop('Expired')
        self.write_status()
        self.assertEqual(self.run_client('work').returncode, 0)
        for value in (None, [], 'missing'):
            peer['sshHostKeys'] = value
            if value == 'missing':
                peer.pop('sshHostKeys')
            self.write_status()
            self.failure('missing-advertised-host-keys')
        for key in ['ssh-ed25519 AAAA\nssh-ed25519 AAAA', 'command=evil ssh-ed25519 AAAA', 'ssh-ed25519 not-base64!', 'ssh-ed25519 AAA']:
            peer['sshHostKeys'] = [key]
            self.write_status()
            self.failure('invalid-schema')
        peer['sshHostKeys'] = ['ssh-ed25519 AAAA']
        for field in ('InNetworkMap', 'Online', 'Expired'):
            for value in ('false', 0, {}, []):
                peer[field] = value
                self.write_status()
                self.failure('invalid-schema')
            peer[field] = False
        peer['InNetworkMap'] = False
        self.write_status()
        self.failure('unknown-selector')

    def test_schema_documents_and_backend_failures(self):
        for raw in ('', '{', '{}', 'null', '[]', '{}\n{}', self.status.read_text() + '\nnull', self.status.read_text() + '\x00'):
            self.write_status(raw)
            self.failure('invalid-schema')
        self.write_status(' ' * 8388609)
        self.failure('invalid-schema')
        for state, failure in [('NeedsLogin', 'logged-out'), ('Stopped', 'stopped/not-ready'), ('Starting', 'stopped/not-ready'), ('UnknownFutureState', 'invalid-schema')]:
            self.snapshot['BackendState'] = state
            self.write_status()
            self.failure(failure)
        self.failure('daemon-unavailable', STATUS_EXIT='37')
        self.snapshot['BackendState'] = 'Running'
        for peer in (None, {}):
            self.snapshot['Peer'] = peer
            self.write_status()
            self.failure('unknown-selector')
        for peer in ('bad', [], 42):
            self.snapshot['Peer'] = peer
            self.write_status()
            self.failure('invalid-schema')
        self.snapshot.pop('Peer')
        self.write_status()
        self.failure('invalid-schema')

    def test_duplicate_id_and_missing_relevant_fields(self):
        base = copy.deepcopy(self.snapshot)
        self.snapshot['Peer']['nodekey:fixture-b']['ID'] = 'nFixtureWork'
        self.write_status()
        self.failure('invalid-schema')
        for field in ('ID', 'DNSName', 'TailscaleIPs', 'InNetworkMap'):
            self.snapshot = copy.deepcopy(base)
            self.snapshot['Peer']['nodekey:fixture-a'].pop(field)
            self.write_status()
            self.failure('invalid-schema')
        self.snapshot = copy.deepcopy(base)
        self.snapshot['Peer']['nodekey:fixture-a'].pop('sshHostKeys')
        self.snapshot['Peer']['nodekey:fixture-a']['SSH_HostKeys'] = ['ssh-ed25519 AAAA']
        self.write_status()
        self.failure('missing-advertised-host-keys')

    def test_schema_fields_reject_final_lf_and_cr(self):
        base = copy.deepcopy(self.snapshot)
        for ending in ('\n', '\r'):
            for field, value in [('ID', 'nFixtureWork' + ending),
                                 ('DNSName', 'work.example.ts.net' + ending),
                                 ('TailscaleIPs', ['100.64.0.20' + ending]),
                                 ('TailscaleIPs', ['fd7a:115c:a1e0::2' + ending]),
                                 ('sshHostKeys', ['ssh-ed25519 AAAA comment' + ending])]:
                with self.subTest(field=field, ending=repr(ending), value=value):
                    self.snapshot = copy.deepcopy(base)
                    self.snapshot['Peer']['nodekey:fixture-a'][field] = value
                    self.write_status()
                    self.failure('invalid-schema')
        self.snapshot = base
        self.write_status()
        p = self.run_client('work')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[-1], [b'ssh', b'100.64.0.20', b'-t', REMOTE.encode()])

    def test_newline_address_cannot_bypass_visible_collision(self):
        base = copy.deepcopy(self.snapshot)
        for address in ('100.64.0.20', 'fd7a:115c:a1e0::2'):
            for ending in ('\n', '\r'):
                with self.subTest(address=address, ending=repr(ending)):
                    self.snapshot = copy.deepcopy(base)
                    self.snapshot['Peer']['nodekey:fixture-a']['TailscaleIPs'] = [address + ending]
                    self.snapshot['Peer']['nodekey:fixture-b']['TailscaleIPs'] = [address]
                    self.write_status()
                    self.failure('invalid-schema')
        self.snapshot['Peer']['nodekey:fixture-a']['TailscaleIPs'] = ['100.64.0.21']
        self.write_status()
        p = self.run_client('work')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[-1], [b'ssh', b'100.64.0.21', b'-t', REMOTE.encode()])

    def test_control_suffix_disables_short_names_without_transport(self):
        for ending in ('\n', '\r'):
            with self.subTest(ending=repr(ending)):
                self.snapshot['CurrentTailnet']['MagicDNSSuffix'] = 'example.ts.net' + ending
                self.write_status()
                self.failure('unknown-selector', 'work')
                p = self.run_client('doctor', 'work.example.ts.net')
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout)['address'], '100.64.0.20')
                self.assertEqual(self.calls(), [[b'status', b'--json'], [b'status', b'--json']])

    def test_alias_data(self):
        hosts = self.home / '.config/tailmux/hosts'
        hosts.parent.mkdir(parents=True)
        hosts.write_text('# aliases\n\n Desk shared.other.ts.net.\n')
        p = self.run_client('doctor', 'DESK')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['peerId'], 'nFixtureShared')
        for body in ['a work\n', 'a b\nb a\n', 'a work.example.ts.net\nA shared.other.ts.net\n',
                     'a $(touch marker)\n', 'a `touch marker`\n', 'a x.example.ts.net ignored\n',
                     'a user@work.example.ts.net\n', 'a -oProxyCommand=evil\n', 'a work.example.ts.net\x00\n', 'x' * 65537]:
            hosts.write_text(body)
            self.failure('invalid-aliases')
        hosts.unlink()
        self.failure('invalid-aliases', TAILMUX_HOSTS_FILE=str(hosts))
        p = self.run_client('work')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.root / 'marker').exists())

    def test_arguments_and_offline_dispatch(self):
        for args in [(), ('--help', 'extra'), ('--version', 'extra'), ('work', 'uname'), ('doctor', 'work', 'extra'),
                     ('-oProxyCommand=evil',), ('user@@work',), ('@work',), ('-x@work',), ('x;id@work',),
                     ('work:22',), ('$(touch marker)',), ('`touch marker`',), ('host name',), ('https://work',)]:
            self.failure('invalid-', *args) if args else None
        p = self.run_client()
        self.assertEqual(p.returncode, 2)
        self.trace.unlink(missing_ok=True)
        p = self.run_client('doctor')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('OpenSSH\tSSH client / OS or package owner\t', p.stdout)
        self.assertIn('vendor patch and OS build evidence required', p.stdout)
        self.assertEqual(self.calls(), [[b'version', b'--daemon', b'--json']])
        self.assertFalse(self.forbidden.exists())
        for name in ('jq', 'tailscale', 'ssh'):
            (self.bin / name).rename(self.bin / (name + '.away'))
        for args in [('--help',), ('--version',), ('-h',), ('-V',)]:
            self.trace.unlink(missing_ok=True)
            p = self.run_client(*args, allow_missing_tailscale=True, TAILMUX_TAILSCALE_SOCKET='bad\nconfig')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(self.calls(), [])
        self.failure('missing-dependency', 'work', allow_missing_tailscale=True)

    def test_relevant_schema_types_and_optional_booleans(self):
        base = copy.deepcopy(self.snapshot)
        for field, value in [('ID', 42), ('ID', ''), ('DNSName', None), ('DNSName', 'x..example'),
                             ('TailscaleIPs', None), ('TailscaleIPs', ['100.64.0.999']),
                             ('TailscaleIPs', ['-oProxyCommand=evil']), ('TailscaleIPs', ['fd7a:::2']),
                             ('sshHostKeys', {}), ('sshHostKeys', [42]), ('Expired', None)]:
            with self.subTest(field=field, value=value):
                self.snapshot = copy.deepcopy(base)
                self.snapshot['Peer']['nodekey:fixture-b'][field] = value
                self.write_status()
                self.failure('invalid-schema')
        for field, value in [('CurrentTailnet', []), ('CurrentTailnet', {'MagicDNSSuffix': 42}), ('BackendState', None)]:
            self.snapshot = copy.deepcopy(base)
            self.snapshot[field] = value
            self.write_status()
            self.failure('invalid-schema')
        for online in (None, 'absent'):
            self.snapshot = copy.deepcopy(base)
            peer = self.snapshot['Peer']['nodekey:fixture-a']
            if online == 'absent':
                peer.pop('Online')
            else:
                peer['Online'] = online
            peer.pop('Expired')
            self.snapshot.pop('CurrentTailnet')
            self.write_status()
            p = self.run_client('doctor', 'work.example.ts.net')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIsNone(json.loads(p.stdout)['online'])
            self.assertIs(json.loads(p.stdout)['expired'], False)

    def test_real_bin_prefix_request_is_normalized_or_refused(self):
        hostile = '/opt/homebrew/bin:$(touch MARKER):' + str(self.bin)
        env = cli_environment(self.bin, self.env, PATH=hostile)
        self.assertEqual(env['PATH'], str(self.bin) + ':' + hostile)
        self.assertEqual(shutil.which('tailscale', path=env['PATH']), str(self.bin / 'tailscale'))
        p = self.run_client('work', PATH=hostile)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[-1][:3], [b'ssh', b'100.64.0.20', b'-t'])
        other = self.root / 'non-private'
        other.mkdir()
        outside = other / 'tailscale'
        outside.write_text('#!/bin/bash\nexit 99\n')
        outside.chmod(0o755)
        (self.bin / 'tailscale').unlink()
        with self.assertRaisesRegex(AssertionError, 'non-private'):
            self.run_client('work', PATH=str(other))
        self.assertFalse((self.root / 'MARKER').exists())

    def test_synthetic_ambient_shell_hooks_do_not_reach_cli(self):
        hook = self.root / 'bash-env'
        sentinel = self.root / 'ambient-hook-ran'
        hook.write_text('printf compromised > "$LEAK_SENTINEL"\n')
        env = {'HOME': str(self.home), 'ZDOTDIR': str(self.home), 'SHELL': '/bin/bash',
               'LC_ALL': 'C', 'TMPDIR': str(self.root),
               'PATH': '/usr/bin:/bin:' + str(Path(shutil.which('jq')).parent),
               'BASH_ENV': str(hook), 'LEAK_SENTINEL': str(sentinel),
               'BASH_FUNC_tailscale%%': '() { printf compromised; }',
               'TAILMUX_SYNTHETIC_TOKEN': 'test-data-only'}
        probe = '''import runpy, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).parent))
for path, classname in [(sys.argv[1], "Runtime"), (sys.argv[2], "Lifecycle")]:
    case = runpy.run_path(path, run_name="environment_probe")[classname]()
    case.setUp()
    try:
        assert "BASH_ENV" not in case.env
        assert "TAILMUX_SYNTHETIC_TOKEN" not in case.env
        assert not any(name.startswith("BASH_FUNC_") for name in case.env)
        if classname == "Runtime":
            result = case.run_client("--version")
        else:
            result = case.run_setup("--version")
        assert result.returncode == 0, result.stderr
        assert result.stdout == "tailmux 0.2.2\\n", result.stdout
    finally:
        case.doCleanups()
'''
        p = subprocess.run([sys.executable, '-c', probe, str(Path(__file__)),
                            str(Path(__file__).with_name('installer_cli.py'))],
                           env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(sentinel.exists())

    def test_each_runtime_dependency_is_required_without_fallback(self):
        for name in ('jq', 'tailscale', 'ssh'):
            original = self.bin / name
            hidden = self.bin / (name + '.hidden')
            original.rename(hidden)
            try:
                self.failure('missing-dependency: ' + name, allow_missing_tailscale=name == 'tailscale')
                self.assertEqual(self.calls(), [])
            finally:
                hidden.rename(original)

    def test_fixed_program_ignores_path_and_attaches_or_creates(self):
        for entry in ('$(touch MARKER)', '`touch MARKER`', '"; touch MARKER; #', "quote'", '/opt/homebrew/bin'):
            self.trace.unlink(missing_ok=True)
            p = self.run_client('work', PATH=entry)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(self.calls()[-1][-1].decode(), REMOTE)
        self.assertFalse((self.root / 'MARKER').exists())
        for attach_exit, expected in [('0', 'attach\n'), ('1', 'attach\nnew\n')]:
            p = subprocess.run(['/bin/bash', '-c', 'tmux() { printf "%s\\n" "$1"; [[ "$1" != attach ]] || return "$ATTACH_EXIT"; }; ' + REMOTE],
                               env=dict(self.env, ATTACH_EXIT=attach_exit), capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, expected)
        p = subprocess.run(['/bin/bash', '-c', REMOTE], env=dict(self.env, PATH=str(self.root / 'absent')), capture_output=True, text=True)
        self.assertEqual(p.returncode, 127)
        self.assertEqual(p.stderr, 'tmux not found on remote\n')

    def test_wrapper_exit_error_and_exec_signal(self):
        for message in ('App Store and TestFlight builds do not support tailscale ssh', 'policy denied', 'host key mismatch'):
            p = self.run_client('work', WRAPPER_EXIT='37', WRAPPER_ERROR=message)
            self.assertEqual(p.returncode, 37)
            self.assertEqual(p.stderr, message + '\n')
        pidfile = self.root / 'pid'
        p = subprocess.Popen(['/bin/bash', str(CLIENT), 'work'], env=cli_environment(self.bin, self.env, EXEC_PID_FILE=str(pidfile)), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if pidfile.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(pidfile.exists())
            self.assertEqual(int(pidfile.read_text()), p.pid)
            p.send_signal(signal.SIGTERM)
            p.communicate(timeout=5)
            self.assertEqual(p.returncode, -signal.SIGTERM)
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate()
        self.assertFalse(self.forbidden.exists())


    def sentry_fixture(self):
        self.report = self.root / 'report'
        self.report_args = self.root / 'report-args'
        self.env.update(REPORT=str(self.report), REPORT_ARGS=str(self.report_args))
        self.script('curl', '''#!/bin/bash
printf '%s\\0' "$@" > "$REPORT_ARGS"
cat > "$REPORT"
printf 'upload output must stay private\\n'
printf 'upload error must stay private\\n' >&2
exit "${REPORT_EXIT:-0}"
''')

    def test_sentry_is_opt_in_and_does_not_report_success_or_input_errors(self):
        self.sentry_fixture()
        self.failure('daemon-unavailable', STATUS_EXIT='37', SENTRY_DSN=SENTRY_DSN)
        self.assertFalse(self.report.exists())
        for args in [('--help',), ('--version',), ('work',), ('unknown-device',), ('invalid;selector',)]:
            self.run_client(*args, TAILMUX_SENTRY_DSN=SENTRY_DSN)
            self.assertFalse(self.report.exists(), args)

    def test_sentry_payload_excludes_request_and_environment_data(self):
        self.sentry_fixture()
        p = self.failure('daemon-unavailable', 'private-user@private-device', STATUS_EXIT='37',
                         TAILMUX_SENTRY_DSN=SENTRY_DSN, TAILMUX_SENTRY_ENVIRONMENT='development',
                         TAILMUX_SENTRY_RELEASE='tailmux@test-commit', PRIVATE_TOKEN='do-not-send')
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, '')
        self.assertEqual(p.stderr, 'tailmux: daemon-unavailable: tailscale status failed\n')
        header, item, event = map(json.loads, self.report.read_text().splitlines())
        self.assertEqual(item['type'], 'event')
        self.assertEqual(header['dsn'], SENTRY_DSN)
        self.assertEqual(header['event_id'], event['event_id'])
        self.assertRegex(event['event_id'], r'^[0-9a-f]{32}$')
        self.assertEqual(event['release'], 'tailmux@test-commit')
        self.assertEqual(event['environment'], 'development')
        exception = event['exception']['values'][0]
        self.assertEqual(exception['type'], 'TailmuxError')
        self.assertEqual(exception['value'], 'daemon-unavailable')
        frame = exception['stacktrace']['frames'][0]
        self.assertEqual(frame['filename'], 'bin/tailmux')
        self.assertRegex(CLIENT.read_text().splitlines()[frame['lineno'] - 1], r'''fail ["']daemon-unavailable:''')
        for private in ('private-user', 'private-device', 'do-not-send', str(self.home), str(self.root), 'tailscale status failed'):
            self.assertNotIn(private, self.report.read_text())
        args = self.report_args.read_bytes().split(b'\0')[:-1]
        self.assertEqual(args[-1], b'https://o123.ingest.de.sentry.io/api/456/envelope/')
        self.assertEqual(args[args.index(b'--max-time') + 1], b'3')
        self.assertNotIn(b'-L', args)
        self.assertEqual(list(self.root.glob('tailmux.*')), [])

    def test_sentry_failure_and_missing_curl_preserve_original_error(self):
        self.sentry_fixture()
        p = self.failure('daemon-unavailable', STATUS_EXIT='37', TAILMUX_SENTRY_DSN=SENTRY_DSN, REPORT_EXIT='28')
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stderr, 'tailmux: daemon-unavailable: tailscale status failed\n')
        self.assertEqual(p.stdout, '')
        (self.bin / 'curl').unlink()
        p = self.failure('daemon-unavailable', STATUS_EXIT='37', TAILMUX_SENTRY_DSN=SENTRY_DSN)
        self.assertEqual(p.returncode, 1)

    def test_sentry_invalid_configuration_does_not_send(self):
        self.sentry_fixture()
        changes = [
            {'TAILMUX_SENTRY_DSN': SENTRY_DSN.replace('https:', 'http:')},
            {'TAILMUX_SENTRY_DSN': SENTRY_DSN + '\n'},
            {'TAILMUX_SENTRY_DSN': SENTRY_DSN + '?query=private'},
            {'TAILMUX_SENTRY_DSN': SENTRY_DSN + '/extra'},
            {'TAILMUX_SENTRY_ENVIRONMENT': 'development"injection'},
            {'TAILMUX_SENTRY_RELEASE': 'release\nprivate'},
        ]
        for change in changes:
            config = {'TAILMUX_SENTRY_DSN': SENTRY_DSN}
            config.update(change)
            self.failure('daemon-unavailable', STATUS_EXIT='37', **config)
            self.assertFalse(self.report.exists(), change)

    def test_sentry_keeps_transport_exit_and_exec_signal_behavior(self):
        self.sentry_fixture()
        self.env['TAILMUX_SENTRY_DSN'] = SENTRY_DSN
        self.test_wrapper_exit_error_and_exec_signal()
        self.assertFalse(self.report.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
