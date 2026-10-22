#!/usr/bin/env python3
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / 'bin/tailmux'
STATUS = ROOT / 'scripts/tests/fixtures/status-v1.104.2/running.json'


class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tailmux-doctor-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.bin = self.root / 'bin'
        self.home = self.root / 'home'
        self.bin.mkdir()
        self.home.mkdir()
        self.trace = self.root / 'trace'
        self.version_file = self.root / 'version.json'
        self.daemon_file = self.root / 'daemon.json'
        self.status_file = self.root / 'status.json'
        self.status_file.write_bytes(STATUS.read_bytes())
        self.version('1.104.2', '1.104.2')
        real_jq = shutil.which('jq')
        self.assertIsNotNone(real_jq, 'development test requires jq')
        for name in ('bash', 'head', 'cat', 'mktemp', 'wc', 'tr', 'rm', 'rmdir'):
            executable = '/bin/bash' if name == 'bash' else shutil.which(name)
            self.assertIsNotNone(executable, name)
            (self.bin / name).symlink_to(executable)
        self.script('jq', f'''if [[ "$*" == --version ]]; then
  printf '%s\\n' "${{JQ_VERSION:-jq-1.8.2}}"
  exit "${{JQ_EXIT:-0}}"
fi
exec {shlex.quote(real_jq)} "$@"
''')
        self.script('tailscale', '''{ printf 'tailscale'; printf ' %s' "$@"; printf '\\n'; } >> "$TRACE"
case "$*" in
  'version --daemon --json') cat "$DAEMON_FILE"; exit "${DAEMON_EXIT:-0}" ;;
  'version --json') cat "$VERSION_FILE"; exit "${CLI_EXIT:-0}" ;;
  'status --json') cat "$STATUS_FILE"; exit "${STATUS_EXIT:-0}" ;;
esac
exit 97
''')
        self.script('ssh', '''if [[ "$*" == -V ]]; then
  printf '%s\\n' "${SSH_VERSION:-OpenSSH_10.3p1, LibreSSL 3.3.6}" >&2
  exit "${SSH_EXIT:-0}"
fi
printf 'forbidden ssh\\n' >> "$TRACE"
exit 97
''')
        for name in ('sudo', 'curl', 'wget', 'brew', 'apt', 'apt-get', 'dnf', 'yum', 'pacman',
                     'systemctl', 'service', 'launchctl', 'mount', 'umount', 'fusermount',
                     'tailscaled', 'tmux', 'python', 'python3', 'env', 'printenv', 'ps', 'kill', 'pkill'):
            self.script(name, f'printf "forbidden {name}\\n" >> "$TRACE"\nexit 97\n')
        self.env = {'HOME': str(self.home), 'PATH': str(self.bin), 'SHELL': '/bin/bash',
                    'LC_ALL': 'C', 'TMPDIR': str(self.root), 'TRACE': str(self.trace),
                    'VERSION_FILE': str(self.version_file), 'DAEMON_FILE': str(self.daemon_file),
                    'STATUS_FILE': str(self.status_file), 'TAILMUX_SYNTHETIC_SECRET': 'do-not-print-fixture-secret'}
        (self.home / 'prefs').write_text('private prefs must remain untouched\n')

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o755)

    def version(self, cli, daemon, **metadata):
        record = {'majorMinorPatch': cli.split('-')[0], 'short': cli.split('-')[0], 'long': cli}
        record.update(metadata)
        self.version_file.write_text(json.dumps(record))
        self.daemon_file.write_text(json.dumps(dict(record, daemonLong=daemon)))

    def run_doctor(self, *selector, missing=(), **changes):
        env = dict(self.env, **changes)
        for name in ('tailscale', 'ssh', 'jq', 'head', 'tr', 'bash'):
            resolved = shutil.which(name, path=env['PATH'])
            self.assertEqual(resolved, None if name in missing else str(self.bin / name))
        before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        result = subprocess.run(['/bin/bash', str(CLIENT), 'doctor', *selector], env=env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        after = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        self.assertNotIn('do-not-print-fixture-secret', result.stdout + result.stderr)
        self.assertNotIn('private prefs', result.stdout + result.stderr)
        self.assertFalse(any(self.root.glob('tailmux.*')), 'private resolver files must be cleaned up')
        self.assertNotIn('forbidden', self.calls())
        return result

    def calls(self):
        return self.trace.read_text() if self.trace.exists() else ''

    def rows(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(lines[3].split('\t'), ['name', 'role/owner', 'active path', 'CLI version',
                                              'daemon version', 'policy classification', 'evidence date', 'reason'])
        rows = [line.split('\t') for line in lines[4:]]
        self.assertTrue(all(len(row) == 8 for row in rows), result.stdout)
        self.assertEqual([row[0] for row in rows], ['Bash', 'jq', 'Tailscale CLI', 'Tailscale daemon',
                                                  'OpenSSH', 'tmux', 'TLS trust'])
        self.assertEqual({row[6] for row in rows}, {'2026-10-22'})
        return {row[0]: row for row in rows}

    def test_supported_baselines_and_local_only_inventory(self):
        rows = self.rows(self.run_doctor())
        self.assertEqual(rows['jq'][2:6], [str(self.bin / 'jq'), '1.8.2', '-', 'supported'])
        self.assertEqual(rows['Tailscale CLI'][2:6], [str(self.bin / 'tailscale'), '1.104.2', '1.104.2', 'supported'])
        self.assertEqual(rows['Tailscale daemon'][2:6], ['unknown (reported through local CLI)', '1.104.2', '1.104.2', 'supported'])
        self.assertEqual(rows['OpenSSH'][3:6], ['OpenSSH_10.3p1', '-', 'unknown'])
        self.assertEqual(rows['tmux'][3:6], ['unknown', '-', 'unknown'])
        self.assertEqual(rows['TLS trust'][5], 'unknown')
        self.assertEqual(self.calls(), 'tailscale version --daemon --json\n')
        self.assertIn('OS security maintenance unknown', rows['Bash'][7])
        self.assertIn('platform compatibility unverified', rows['Tailscale CLI'][7])

    def test_vendor_builds_and_unreviewed_versions_are_unknown(self):
        for version in ('1.102.3-vendor-backport', '1.104.2-vendor', '1.106.0', '1.104.2-dev20261022'):
            with self.subTest(version=version):
                self.version(version, version)
                rows = self.rows(self.run_doctor())
                self.assertEqual(rows['Tailscale CLI'][5], 'unknown')
                self.assertEqual(rows['Tailscale daemon'][5], 'unknown')
        self.version('1.104.2-te26db7a57', '1.104.2-te26db7a57')
        self.assertEqual(self.rows(self.run_doctor())['Tailscale CLI'][5], 'supported')
        self.version('1.104.2', '1.104.2', isDev=True)
        self.assertEqual(self.rows(self.run_doctor())['Tailscale CLI'][5], 'unknown')

    def test_unsupported_is_not_an_exploit_claim(self):
        self.version('1.105.0', '1.105.0')
        rows = self.rows(self.run_doctor(JQ_VERSION='jq-1.7.1'))
        self.assertEqual(rows['jq'][5], 'unsupported')
        self.assertIn('no vulnerability conclusion', rows['jq'][7])
        self.assertEqual(rows['Tailscale CLI'][5], 'unsupported')

    def test_advisory_ranges_retain_conditions(self):
        for version, expected, excluded in (
            ('1.102.3', ['TS-2026-013', 'compromised certificates', 'exposure unverified'], ['TS-2026-011', 'TS-2026-010']),
            ('1.102.1', ['TS-2026-011', '4via6'], ['TS-2026-010', 'TS-2026-005']),
            ('1.98.9', ['TS-2026-010', 'acceptEnv'], ['TS-2026-005', 'TS-2026-009/006']),
            ('1.98.8', ['TS-2026-009/006', 'nonroot', 'TS-2026-005', 'Serve operator'], []),
        ):
            with self.subTest(version=version):
                self.version(version, version)
                row = self.rows(self.run_doctor())['Tailscale daemon']
                self.assertEqual(row[5], 'advisory-affected')
                for text in expected:
                    self.assertIn(text, row[7])
                for text in excluded:
                    self.assertNotIn(text, row[7])

    def test_mismatch_retains_individual_versions_and_policies(self):
        self.version('1.104.2', '1.102.3')
        rows = self.rows(self.run_doctor())
        self.assertEqual(rows['Tailscale CLI'][3:6], ['1.104.2', '1.102.3', 'supported'])
        self.assertEqual(rows['Tailscale daemon'][3:6], ['1.104.2', '1.102.3', 'advisory-affected'])
        self.assertIn('CLI/daemon mismatch', rows['Tailscale daemon'][7])
        self.assertEqual(self.calls(), 'tailscale version --daemon --json\n')

    def test_failed_daemon_probe_retains_only_successful_cli_identity(self):
        rows = self.rows(self.run_doctor(DAEMON_EXIT='37'))
        self.assertEqual(rows['Tailscale CLI'][3:6], ['1.104.2', 'unknown', 'supported'])
        self.assertEqual(rows['Tailscale daemon'][5], 'unknown')
        self.assertEqual(self.calls(), 'tailscale version --daemon --json\ntailscale version --json\n')
        rows = self.rows(self.run_doctor(DAEMON_EXIT='37', CLI_EXIT='37', SSH_EXIT='37', JQ_EXIT='37'))
        for name in ('Tailscale CLI', 'Tailscale daemon', 'OpenSSH', 'jq'):
            self.assertEqual(rows[name][5], 'unknown')

    def test_malformed_missing_oversized_and_conflicting_metadata(self):
        for raw in ('{', '{}', 'null', '[]', '{}\n{}', self.daemon_file.read_text() + '\x00',
                    json.dumps({'long': '1.104.2', 'short': '1.102.3', 'majorMinorPatch': '1.102.3'}),
                    json.dumps({'long': '1.104.2\nsecret', 'short': '1.104.2', 'majorMinorPatch': '1.104.2'})):
            with self.subTest(raw=raw[:60]):
                self.daemon_file.write_text(raw)
                rows = self.rows(self.run_doctor())
                self.assertEqual(rows['Tailscale CLI'][5], 'unknown')
                self.assertEqual(rows['Tailscale daemon'][5], 'unknown')
        for oversized in (' ' * 65538, self.version_file.read_text() + '\n' * 65538):
            self.daemon_file.write_text(oversized)
            rows = self.rows(self.run_doctor())
            self.assertEqual(rows['Tailscale CLI'][5], 'supported')
            self.assertEqual(rows['Tailscale daemon'][5], 'unknown')
        self.daemon_file.write_text(self.version_file.read_text())
        rows = self.rows(self.run_doctor())
        self.assertEqual(rows['Tailscale CLI'][5], 'supported')
        self.assertEqual(rows['Tailscale daemon'][5], 'unknown')
        rows = self.rows(self.run_doctor(JQ_VERSION='jq-unknown', SSH_VERSION='private unexpected banner'))
        self.assertEqual(rows['jq'][3], 'unknown')
        self.assertEqual(rows['OpenSSH'][3], 'unknown')
        self.assertNotIn('private unexpected banner', rows['OpenSSH'])

    def test_missing_dependencies_still_report_inventory(self):
        for command, row_name in (('jq', 'jq'), ('tailscale', 'Tailscale CLI'), ('ssh', 'OpenSSH'), ('head', 'jq')):
            with self.subTest(command=command):
                original = self.bin / command
                hidden = self.bin / (command + '.hidden')
                original.rename(hidden)
                try:
                    rows = self.rows(self.run_doctor(missing=(command,)))
                    self.assertEqual(rows[row_name][5], 'unknown' if command == 'head' else 'unsupported')
                finally:
                    hidden.rename(original)

    def test_selector_keeps_resolution_only_and_fails_closed(self):
        result = self.run_doctor('work')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['peerId'], 'nFixtureWork')
        self.assertEqual(self.calls(), 'tailscale status --json\n')
        for selector, error in (('8.8.8.8', 'unknown-selector'), ('-bad', 'invalid-request')):
            self.trace.unlink(missing_ok=True)
            result = self.run_doctor(selector, TAILMUX_LAN_FALLBACK='1')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            self.assertIn(self.calls(), ('', 'tailscale status --json\n'))
        self.trace.unlink(missing_ok=True)
        result = self.run_doctor('work', STATUS_EXIT='37')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('daemon-unavailable', result.stderr)
        self.assertEqual(self.calls(), 'tailscale status --json\n')

    def test_fixture_refuses_nonprivate_resolution(self):
        (self.bin / 'tailscale').unlink()
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'tailscale').write_text('#!/bin/bash\nexit 99\n')
        (outside / 'tailscale').chmod(0o755)
        with self.assertRaises(AssertionError):
            self.run_doctor(PATH=str(outside) + ':' + str(self.bin))


if __name__ == '__main__':
    unittest.main(verbosity=2)
