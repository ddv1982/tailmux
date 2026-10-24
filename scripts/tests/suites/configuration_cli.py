#!/usr/bin/env python3
import json
from pathlib import Path
import os
import shutil
import subprocess
import signal
import time
import unittest

import runtime_cli
import installer_cli

ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / 'bin/tailmux'


class Configuration(unittest.TestCase):
    def setUp(self):
        self.fx = runtime_cli.Runtime()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.home, self.bin, self.root = self.fx.home, self.fx.bin, self.fx.root
        self.config = self.home / '.config/tailmux/config'
        for name in ('mkdir', 'mv', 'chmod', 'cmp'):
            (self.bin / name).symlink_to(shutil.which(name))

    def run_cli(self, *args, **changes):
        return self.fx.run_client(*args, **changes)

    def ok(self, *args, **changes):
        result = self.run_cli(*args, **changes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def save(self, data):
        self.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config.write_bytes(data)
        self.config.chmod(0o600)

    def test_persistence_and_literal_argv(self):
        socket = '/space ü \' " *?[x] ;$(touch marker)`id`.sock'
        self.ok('--config', 'set', 'socket', socket)
        self.assertEqual(self.config.read_bytes(), f'tailmux-config-v1\nsocket={socket}\n'.encode())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.parent.stat().st_mode & 0o777, 0o700)
        self.ok('Alice@work')
        prefix = f'--socket={socket}'.encode()
        self.assertEqual(self.fx.calls(), [[prefix, b'status', b'--json'],
                                          [prefix, b'ssh', b'Alice@100.64.0.20', b'-t', runtime_cli.REMOTE.encode()]])
        self.assertFalse((self.root / 'marker').exists())

    def test_override_bypasses_fifo_and_empty_override_fails(self):
        self.config.parent.mkdir(parents=True)
        os.mkfifo(self.config)
        self.ok('doctor', 'work', TAILMUX_TAILSCALE_SOCKET='/override')
        self.assertEqual(self.fx.calls(), [[b'--socket=/override', b'status', b'--json']])
        self.fx.trace.unlink()
        result = self.run_cli('work', TAILMUX_TAILSCALE_SOCKET='')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.fx.calls(), [])
        result = self.run_cli('work')
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(self.config), result.stderr)
        self.assertEqual(self.fx.calls(), [])

    def test_reset_repairs_current_version_with_verified_backup(self):
        data = b'tailmux-config-v1\nsocket=relative\nextra\x00\n'
        self.save(data)
        result = self.run_cli('work')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.fx.calls(), [])
        result = self.run_cli('--config', 'show', TAILMUX_TAILSCALE_SOCKET='')
        self.assertIn('--config reset socket', result.stdout + result.stderr)
        self.ok('--config', 'reset', 'socket', TAILMUX_TAILSCALE_SOCKET='relative')
        self.assertFalse(self.config.exists())
        backups = list(self.config.parent.glob('config.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), data)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.fx.calls(), [])

    def test_show_default_saved_override_and_path_without_invocation(self):
        result = self.ok('--config', 'show')
        self.assertIn('Saved socket: unset\nSaved state: absent\n', result.stdout)
        self.assertIn('Source: native default\n', result.stdout)
        self.assertIn(f'PATH-selected CLI: {self.bin / "tailscale"}\n', result.stdout)
        self.ok('--config', 'set', 'socket', '/saved')
        result = self.ok('--config', 'show')
        self.assertIn('Saved socket: /saved\nSaved state: valid\nEffective socket: /saved\nSource: saved\n', result.stdout)
        result = self.ok('--config', 'show', TAILMUX_TAILSCALE_SOCKET='/override')
        self.assertIn('Effective socket: /override\nSource: environment\n', result.stdout)
        self.assertIn('Environment overrides saved', result.stdout)
        self.ok('--config', 'reset', 'socket', TAILMUX_TAILSCALE_SOCKET='')
        result = self.ok('--config', 'show', TAILMUX_TAILSCALE_SOCKET='/override')
        self.assertIn('Saved state: absent', result.stdout)
        self.assertIn('Source: environment', result.stdout)
        self.ok('--config', 'reset', 'socket')
        self.assertEqual(self.fx.calls(), [])

    def test_bad_environment_does_not_block_set_reset_or_inspection(self):
        self.ok('--config', 'set', 'socket', '/saved', TAILMUX_TAILSCALE_SOCKET='bad')
        result = self.run_cli('--config', 'show', TAILMUX_TAILSCALE_SOCKET='')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Saved socket: /saved', result.stdout)
        self.assertIn('Source: environment', result.stdout)
        self.assertIn('Effective socket: invalid', result.stdout)
        self.ok('--config', 'reset', 'socket', TAILMUX_TAILSCALE_SOCKET='bad')
        self.assertEqual(self.fx.calls(), [])

    def test_absent_home_hierarchy_reaches_existing_root_without_hanging(self):
        missing_top = Path('/') / f'{self.root.name}-absent'
        self.assertFalse(missing_top.exists())
        for home in (missing_top / 'nested/home', self.root / 'missing/nested/home'):
            with self.subTest(home=str(home)):
                env = runtime_cli.cli_environment(self.bin, self.fx.env, HOME=str(home))
                result = subprocess.run(['/bin/bash', str(CLIENT), '--config', 'show'],
                                        env=env, cwd=self.root, capture_output=True,
                                        text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'Config file: {home}/.config/tailmux/config\n', result.stdout)
                self.assertIn('Saved state: absent\n', result.stdout)
                self.assertIn('Source: native default\n', result.stdout)
                self.assertFalse(home.exists())
                self.assertEqual(self.fx.calls(), [])
                self.assertFalse(self.fx.forbidden.exists())

    def test_exact_grammar_and_control_bytes(self):
        bad = [b'', b'tailmux-config-v1', b'tailmux-config-v1\nsocket=/a',
               b'tailmux-config-v1\nsocket=/a\n\n', b'tailmux-config-v1\nsocket=\n',
               b'tailmux-config-v1\nsocket=relative\n', b'tailmux-config-v1\nsocket=/a\nsocket=/b\n',
               b'tailmux-config-v1\nother=/a\n', b'tailmux-config-v1\r\nsocket=/a\n']
        bad += [b'tailmux-config-v1\nsocket=/a' + bytes([c]) + b'z\n' for c in [*range(32), 127]]
        for data in bad:
            with self.subTest(data=data):
                self.save(data)
                result = self.run_cli('work')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(str(self.config), result.stderr)
                self.assertEqual(self.fx.calls(), [])
                self.assertEqual(self.config.read_bytes(), data)
        self.save(b'tailmux-config-v1\nsocket=/valid\n')
        self.ok('doctor', 'work')
        self.assertEqual(self.fx.calls(), [[b'--socket=/valid', b'status', b'--json']])

    def test_reset_repairs_header_only_and_missing_record_terminator(self):
        for data in (b'tailmux-config-v1', b'tailmux-config-v1\n', b'tailmux-config-v1\nsocket=/saved'):
            self.save(data)
            self.ok('--config', 'reset', 'socket')
            self.assertFalse(self.config.exists())
            self.assertIn(data, [p.read_bytes() for p in self.config.parent.glob('config.backup.*')])
        self.assertEqual(self.fx.calls(), [])

    def test_unknown_version_never_discarded(self):
        for data in (b'tailmux-config-v2\nsocket=/future\n', b'future-format\n', b''):
            with self.subTest(data=data):
                self.save(data)
                for args in [('--config', 'set', 'socket', '/new'), ('--config', 'reset', 'socket')]:
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(str(self.config), result.stderr)
                    self.assertIn('unknown', result.stderr)
                    self.assertEqual(self.config.read_bytes(), data)
                self.assertEqual(list(self.config.parent.glob('config.backup.*')), [])
        self.assertEqual(self.fx.calls(), [])

    def test_environment_skips_malformed_and_unsafe_lower_priority_data(self):
        self.save(b'tailmux-config-v1\nsocket=invalid\n')
        for data in (b'tailmux-config-v2\n', b'bad\x00data'):
            self.config.write_bytes(data)
            self.ok('doctor', 'work', TAILMUX_TAILSCALE_SOCKET='/override')
        self.config.chmod(0o666)
        self.ok('doctor', 'work', TAILMUX_TAILSCALE_SOCKET='/override')
        self.assertTrue(all(call == [b'--socket=/override', b'status', b'--json'] for call in self.fx.calls()))

    def test_boundaries_and_set_validation(self):
        overhead = len(b'tailmux-config-v1\nsocket=\n')
        socket = '/' + 'x' * (8192 - overhead - 1)
        self.ok('--config', 'set', 'socket', socket)
        self.assertEqual(self.config.stat().st_size, 8192)
        self.ok('--config', 'show')
        for value in ('', 'relative', socket + 'x', '/a\n', '/a\t', '/a\x7f'):
            result = self.run_cli('--config', 'set', 'socket', value)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.config.stat().st_size, 8192)
        data = b'tailmux-config-v1\nsocket=/' + b'x' * 8192 + b'\n'
        self.config.write_bytes(data)
        for args in [('work',), ('--config', 'show'), ('--config', 'reset', 'socket'), ('--config', 'set', 'socket', '/new')]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.config.read_bytes(), data)
        self.assertEqual(self.fx.calls(), [])

    def test_nonregular_links_permissions_and_ancestors(self):
        self.save(b'tailmux-config-v1\nsocket=/safe\n')
        data = self.config.read_bytes()
        target = self.root / 'target'
        target.write_bytes(data)
        self.config.unlink()
        variants = ['symlink', 'dangling', 'fifo', 'directory', 'hardlink', 'writable', 'readable']
        for variant in variants:
            with self.subTest(variant=variant):
                if variant == 'symlink': self.config.symlink_to(target)
                elif variant == 'dangling': self.config.symlink_to(self.root / 'missing')
                elif variant == 'fifo': os.mkfifo(self.config)
                elif variant == 'directory': self.config.mkdir()
                elif variant == 'hardlink': os.link(target, self.config)
                else:
                    self.config.write_bytes(data)
                    self.config.chmod(0o666 if variant == 'writable' else 0o644)
                for args in [('work',), ('--config', 'show'), ('--config', 'reset', 'socket'), ('--config', 'set', 'socket', '/new')]:
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn(str(self.config), result.stdout + result.stderr)
                if self.config.is_dir(): self.config.rmdir()
                else: self.config.unlink()
        self.config.parent.rmdir()
        self.config.parent.symlink_to(self.root)
        self.assertEqual(self.run_cli('--config', 'set', 'socket', '/new').returncode, 2)
        self.assertFalse((self.root / 'config').exists())
        self.config.parent.unlink()
        self.config.parent.mkdir(mode=0o777)
        self.config.parent.chmod(0o777)
        self.assertEqual(self.run_cli('--config', 'set', 'socket', '/new').returncode, 2)
        self.assertEqual(self.fx.calls(), [])

    def test_failed_and_empty_reader_tools_are_not_absence(self):
        self.save(b'tailmux-config-v1\nsocket=/saved\n')
        original = self.config.read_bytes()
        for name in ('stat', 'ls', 'head', 'tr'):
            real = shutil.which(name)
            for body in ('exit 42', 'exit 0', 'printf "tailmux-config-v1\\nsocket=/saved\\n"; exit 42'):
                with self.subTest(name=name, body=body):
                    (self.bin / name).unlink()
                    self.fx.script(name, '#!/bin/bash\n' + body + '\n')
                    result = self.run_cli('work')
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(self.config.read_bytes(), original)
                    self.assertEqual(self.fx.calls(), [])
                    (self.bin / name).unlink()
                    (self.bin / name).symlink_to(real)

    def test_local_config_failures_never_report_to_sentry(self):
        self.fx.script('curl', '#!/bin/bash\nprintf forbidden-curl >> "$FORBIDDEN"\nexit 97\n')
        self.save(b'tailmux-config-v1\nsocket=relative\n')
        changes = dict(TAILMUX_SENTRY_DSN=runtime_cli.SENTRY_DSN)
        for args in [('--config', 'show'), ('--config', 'set', 'socket', '/new'), ('--config', 'set', 'socket', 'relative'), ('--config',)]:
            result = self.run_cli(*args, **changes)
            self.assertEqual(result.returncode, 2)
        (self.bin / 'mktemp').unlink()
        self.fx.script('mktemp', '#!/bin/bash\nexit 42\n')
        result = self.run_cli('--config', 'reset', 'socket', **changes)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.fx.forbidden.exists())
        self.assertEqual(self.fx.calls(), [])
        self.assertFalse((self.config.parent / '.config-lock').exists())

    def test_publication_failure_and_retry_preserve_complete_records(self):
        self.ok('--config', 'set', 'socket', '/old')
        (self.bin / 'mv').unlink()
        self.fx.script('mv', '#!/bin/bash\nexit 42\n')
        result = self.run_cli('--config', 'set', 'socket', '/new')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/old\n')
        self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(list(self.config.parent.glob('.config-stage.*')), [])
        (self.bin / 'mv').unlink()
        (self.bin / 'mv').symlink_to(shutil.which('mv'))
        self.ok('--config', 'set', 'socket', '/new')
        self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/new\n')
        self.assertEqual(self.fx.calls(), [])

    def assert_false_success_publication_is_cleaned(self, value):
        self.ok('--config', 'set', 'socket', '/old')
        original = self.config.read_bytes()
        older_stage = self.config.parent / '.config-stage.previous'
        older_stage.write_bytes(b'previous writer evidence\n')
        older_stage.chmod(0o600)
        (self.bin / 'mv').unlink()
        self.fx.script('mv', '#!/bin/bash\nexit 0\n')
        self.fx.script('curl', '#!/bin/bash\nprintf forbidden-curl >> "$FORBIDDEN"\nexit 97\n')
        result = self.run_cli('--config', 'set', 'socket', value,
                              TAILMUX_SENTRY_DSN=runtime_cli.SENTRY_DSN)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(older_stage.read_bytes(), b'previous writer evidence\n')
        self.assertEqual(self.fx.calls(), [])
        self.assertFalse(self.fx.forbidden.exists())
        self.assertEqual((result.returncode, sorted(p.name for p in self.config.parent.glob('.config-stage.*'))),
                         (2, ['.config-stage.previous']), result.stdout + result.stderr)
        self.assertIn('cannot verify published', result.stderr)
        self.assertNotIn('Saved socket:', result.stdout)

    def test_false_success_publication_changed_value_cleans_current_stage(self):
        self.assert_false_success_publication_is_cleaned('/new')

    def test_false_success_publication_same_value_cleans_current_stage(self):
        self.assert_false_success_publication_is_cleaned('/old')

    def test_backup_verification_failure_preserves_data(self):
        self.save(b'tailmux-config-v1\nsocket=broken\nextra\x00\n')
        data = self.config.read_bytes()
        (self.bin / 'cmp').unlink()
        self.fx.script('cmp', '#!/bin/bash\nexit 42\n')
        result = self.run_cli('--config', 'reset', 'socket')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.config.read_bytes(), data)
        self.assertIn('preserved', result.stderr)
        self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(self.fx.calls(), [])

    def test_own_acquisition_failure_cleans_lock_unknown_lock_stays(self):
        real = shutil.which('stat')
        (self.bin / 'stat').unlink()
        self.fx.script('stat', '#!/bin/bash\nfor arg; do [[ "$arg" != */.config-lock ]] || exit 42; done\nexec ' + real + ' "$@"\n')
        result = self.run_cli('--config', 'set', 'socket', '/new')
        self.assertEqual(result.returncode, 2)
        lock = self.config.parent / '.config-lock'
        self.assertFalse(lock.exists())
        (self.bin / 'stat').unlink()
        (self.bin / 'stat').symlink_to(real)
        lock.mkdir()
        (lock / 'unknown').write_bytes(b'owner evidence')
        for args in [('--config', 'set', 'socket', '/new'), ('--config', 'reset', 'socket')]:
            self.assertEqual(self.run_cli(*args).returncode, 2)
            self.assertEqual((lock / 'unknown').read_bytes(), b'owner evidence')
        self.assertEqual(self.fx.calls(), [])

    def wait_path(self, path, process):
        deadline = time.monotonic() + 5
        while not path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), process.communicate(timeout=2) if process.poll() is not None else 'writer did not reach publication')

    def paused_writer(self):
        (self.bin / 'mv').unlink()
        (self.bin / 'mv').symlink_to(shutil.which('mv'))
        self.ok('--config', 'set', 'socket', '/old')
        (self.bin / 'mv').unlink()
        self.fx.script('mv', '#!/bin/bash\nprintf ready > "$HOME/ready"\nwhile [[ ! -f "$HOME/go" ]]; do /bin/sleep 0.02; done\nexec /bin/mv "$@"\n')
        process = subprocess.Popen(['/bin/bash', str(CLIENT), '--config', 'set', 'socket', '/new'],
                                   env=self.fx.env, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and (process.kill(), process.communicate(timeout=5)))
        self.wait_path(self.home / 'ready', process)
        return process

    def test_competing_writers_and_atomic_publication(self):
        process = self.paused_writer()
        result = self.run_cli('--config', 'set', 'socket', '/other')
        self.assertEqual(result.returncode, 2)
        self.assertIn('writer locked', result.stderr)
        self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/old\n')
        self.ok('doctor', 'work')
        (self.home / 'go').touch()
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/new\n')
        self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(self.fx.calls(), [[b'--socket=/old', b'status', b'--json']])

    def test_sigterm_cleans_own_lock_sigkill_leaves_fail_closed(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(sig=sig):
                (self.home / 'ready').unlink(missing_ok=True)
                (self.home / 'go').unlink(missing_ok=True)
                process = self.paused_writer()
                process.send_signal(sig)
                (self.home / 'go').touch()
                process.communicate(timeout=5)
                lock = self.config.parent / '.config-lock'
                self.assertEqual(lock.exists(), sig == signal.SIGKILL)
                self.assertNotEqual(process.returncode, 0)
                if sig == signal.SIGKILL:
                    self.assertEqual(self.run_cli('--config', 'reset', 'socket').returncode, 2)

    def test_offline_dispatch_and_config_peer_selector(self):
        self.save(b'tailmux-config-v1\nsocket=broken\n')
        for name in ('jq', 'tailscale', 'ssh', 'stat', 'ls', 'head', 'tr'):
            (self.bin / name).unlink()
        for args in [('--help',), ('--version',), ('-h',), ('-V',)]:
            result = self.run_cli(*args, allow_missing_tailscale=True, TAILMUX_TAILSCALE_SOCKET='')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.fx.calls(), [])

    def test_saved_socket_preserves_exec_pid_signals_exit_stderr(self):
        self.ok('--config', 'set', 'socket', '/saved')
        self.fx.test_wrapper_exit_error_and_exec_signal()
        self.assertTrue(all(call[0] == b'--socket=/saved' for call in self.fx.calls()))

    def test_config_is_still_a_peer_selector_and_hosts_are_fixture_only(self):
        self.fx.snapshot['Peer']['nodekey:fixture-a']['DNSName'] = 'config.example.ts.net.'
        self.fx.write_status()
        self.ok('--config', 'set', 'socket', '/saved')
        hosts = self.config.parent / 'hosts'
        hosts.write_bytes(b'desk config.example.ts.net\n')
        result = self.ok('doctor', 'config')
        self.assertEqual(json.loads(result.stdout)['canonicalDNS'], 'config.example.ts.net')
        self.ok('desk')
        self.assertEqual(self.fx.calls()[-1][:3], [b'--socket=/saved', b'ssh', b'100.64.0.20'])

    def test_saved_endpoint_failure_never_tries_default(self):
        self.ok('--config', 'set', 'socket', '/missing')
        result = self.run_cli('work', EXPECTED_SOCKET='/working', SELECTED_STATUS_FIXTURE=str(self.fx.status))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('daemon-unavailable', result.stderr)
        self.assertIn('source saved', result.stderr)
        self.assertEqual(self.fx.calls(), [[b'--socket=/missing', b'status', b'--json']])

    def test_reset_failure_retains_original_and_verified_backup(self):
        self.save(b'tailmux-config-v1\nsocket=/saved\n')
        original = self.config.read_bytes()
        (self.bin / 'rm').unlink()
        for status in (0, 42):
            self.fx.script('rm', f'#!/bin/bash\nexit {status}\n')
            result = self.run_cli('--config', 'reset', 'socket')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.config.read_bytes(), original)
            backups = list(self.config.parent.glob('config.backup.*'))
            self.assertTrue(backups)
            self.assertTrue(all(p.read_bytes() == original for p in backups))
            self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(self.fx.calls(), [])

    @unittest.skipUnless(os.uname().sysname == 'Darwin', 'native macOS ACL fixture')
    def test_mutating_acls_refuse_reads_and_writes(self):
        self.save(b'tailmux-config-v1\nsocket=/saved\n')
        for target in (self.config, self.config.parent):
            subprocess.run(['/bin/chmod', '+a', 'everyone allow write', str(target)], check=True)
            try:
                for args in [('work',), ('--config', 'set', 'socket', '/new'), ('--config', 'reset', 'socket')]:
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/saved\n')
            finally:
                subprocess.run(['/bin/chmod', '-N', str(target)], check=True)
        self.assertEqual(self.fx.calls(), [])

    def test_local_commands_work_without_transport_dependencies(self):
        for name in ('jq', 'tailscale', 'ssh'):
            (self.bin / name).unlink()
        self.ok('--config', 'set', 'socket', '/saved', allow_missing_tailscale=True)
        result = self.ok('--config', 'show', allow_missing_tailscale=True)
        self.assertIn('PATH-selected CLI: unavailable', result.stdout)
        self.ok('--config', 'reset', 'socket', allow_missing_tailscale=True)
        self.assertEqual(self.fx.calls(), [])

    def test_empty_or_failed_staging_output_releases_lock(self):
        self.ok('--config', 'set', 'socket', '/old')
        (self.bin / 'mktemp').unlink()
        for status in (0, 42):
            self.fx.script('mktemp', f'#!/bin/bash\nexit {status}\n')
            result = self.run_cli('--config', 'set', 'socket', '/new')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.config.read_bytes(), b'tailmux-config-v1\nsocket=/old\n')
            self.assertFalse((self.config.parent / '.config-lock').exists())
        self.assertEqual(self.fx.calls(), [])

    def test_fresh_bash_and_zsh_processes_use_saved_selection(self):
        self.ok('--config', 'set', 'socket', '/saved')
        shells = [('/bin/bash', '--noprofile', '--norc')]
        if Path('/bin/zsh').exists():
            shells.append(('/bin/zsh', '-f'))
        for shell in shells:
            self.fx.trace.unlink(missing_ok=True)
            result = subprocess.run([*shell, '-c', 'exec /bin/bash "$1" doctor work', 'fresh', str(CLIENT)],
                                    env=self.fx.env, cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['address'], '100.64.0.20')
            self.assertEqual(self.fx.calls(), [[b'--socket=/saved', b'status', b'--json']])


class InstalledConfiguration(unittest.TestCase):
    def test_configuration_survives_owned_update_and_uninstall(self):
        life = installer_cli.Lifecycle()
        life.setUp()
        self.addCleanup(life.doCleanups)
        (life.bin / 'head').symlink_to(shutil.which('head'))
        life.rc.write_bytes(b'# unrelated fixture shell content\n')
        before_rc = life.rc.read_bytes()
        life.success('install')
        installed = life.prefix / 'tailmux'
        result = subprocess.run(['/bin/bash', str(installed), '--config', 'set', 'socket', '/installed saved'],
                                env=life.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = life.home / '.config/tailmux/config'
        hosts = config.parent / 'hosts'
        hosts.write_bytes(b'desk work.example.ts.net\n')
        original = config.read_bytes()
        self.assertEqual(original, b'tailmux-config-v1\nsocket=/installed saved\n')
        life.older_owned()
        life.success('install', '--replace-owned')
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        result = subprocess.run(['/bin/bash', str(installed), '--config', 'show'],
                                env=life.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Effective socket: /installed saved\nSource: saved', result.stdout)
        (life.bin / 'jq').symlink_to(shutil.which('jq'))
        life.script('tailscale', '''#!/bin/bash
printf '%s\\0' "$@" >> "$TRANSPORT_TRACE"
printf '\\n' >> "$TRANSPORT_TRACE"
[[ "$1" == '--socket=/installed saved' ]] || exit 98
shift
case "$1" in
  status) cat "$STATUS_FIXTURE" ;;
  ssh) printf '%s\\n' 'installed fixture exit' >&2; exit 37 ;;
  *) exit 97 ;;
esac
''')
        trace = life.root / 'transport'
        env = installer_cli.cli_environment(life.bin, life.env, TRANSPORT_TRACE=str(trace),
                                             STATUS_FIXTURE=str(runtime_cli.FIXTURE))
        result = subprocess.run(['/bin/bash', str(installed), 'work'], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertEqual(result.stderr, 'installed fixture exit\n')
        calls = [line.split(b'\0')[:-1] for line in trace.read_bytes().split(b'\n') if line]
        self.assertEqual(calls, [[b'--socket=/installed saved', b'status', b'--json'],
                                 [b'--socket=/installed saved', b'ssh', b'100.64.0.20', b'-t', runtime_cli.REMOTE.encode()]])
        life.success('uninstall')
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(hosts.read_bytes(), b'desk work.example.ts.net\n')
        self.assertEqual(life.rc.read_bytes(), before_rc)
        self.assertFalse(installed.exists())
        self.assertFalse(life.trace.exists())


if __name__ == '__main__':
    unittest.main()
