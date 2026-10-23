#!/usr/bin/env python3
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import signal
import time
import unittest

from fixture_env import cli_environment

ROOT = Path(__file__).resolve().parents[3]
SETUP = ROOT / 'setup.sh'
FIXTURES = ROOT / 'scripts/tests/fixtures'
FORBIDDEN = ('curl wget sudo su doas brew apt apt-get dnf yum pacman zypper apk port systemctl '
             'service launchctl defaults osascript open tailscale tailscaled ssh mount mount_webdav '
             'umount fusermount git').split()
CENSUS = ['alias tailmux=other\n', 'alias -- tailmux=other\n', "alias 'tailmux=other'\n",
          "alias 'tailmux'=other\n", 'alias tailmux\\=other\n', 'alias \\\n  tailmux=other\n', 'alias other=x\n']


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tailmux-life-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'
        self.bin = self.root / 'tools'
        self.home.mkdir()
        self.bin.mkdir()
        self.prefix = self.home / '.local/bin'
        self.trace = self.root / 'forbidden'
        for name in ('bash dirname uname stat ls tr cmp shasum sha256sum dd cat mkdir rmdir mktemp cp mv rm cut xattr wc grep chmod lsattr python3').split():
            tool = shutil.which(name)
            if tool:
                (self.bin / name).symlink_to(tool)
        for name in FORBIDDEN:
            self.script(name, '#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$FORBIDDEN_TRACE"\nexit 97\n')
        self.env = {'HOME': str(self.home), 'ZDOTDIR': str(self.home), 'SHELL': '/bin/bash',
                    'PATH': str(self.bin), 'LC_ALL': 'C', 'TMPDIR': str(self.root),
                    'FORBIDDEN_TRACE': str(self.trace)}
        self.rc = self.home / '.profile'

    def script(self, name, body):
        p = self.bin / name
        p.unlink(missing_ok=True)
        p.write_text(body)
        p.chmod(0o755)

    def run_setup(self, *args, setup=SETUP, **changes):
        p = subprocess.run(['/bin/bash', str(setup), *args], env=cli_environment(self.bin, self.env, **changes),
                           capture_output=True, text=True, timeout=20)
        self.assertFalse(self.trace.exists(), self.trace.read_text() if self.trace.exists() else '')
        return p

    def success(self, *args, **changes):
        p = self.run_setup(*args, **changes)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def refusal(self, *args, contains=None, **changes):
        p = self.run_setup(*args, **changes)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        if contains:
            self.assertIn(contains, p.stdout + p.stderr)
        self.assertNotIn('Client installed at', p.stdout)
        self.assertNotIn('Client uninstall complete', p.stdout)
        return p

    def tree(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*'))

    def test_offline_dispatch_without_modules(self):
        setup = self.root / 'setup.sh'
        setup.write_bytes(SETUP.read_bytes())
        for option in ('--help', '-h', '--version', '-V'):
            p = self.success(option, setup=setup)
            self.assertIn('0.2.0', p.stdout)
        self.refusal('update', setup=setup, contains='deprecated')
        self.refusal('install', setup=setup, contains='Required module missing')
        self.refusal('--help', 'extra', setup=setup)
        self.refusal('install', '--prefix', 'relative')
        self.assertEqual(self.tree(), [])
        p = subprocess.run(['/bin/bash', '-c', 'bash <(cat "$1") install', 'bash', str(SETUP)],
                           env=cli_environment(self.bin, self.env), capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('remote/process-substitution setup is disabled', p.stderr)
        self.assertEqual(self.tree(), [])

    def test_fresh_repeat_uninstall_and_unrelated_bytes(self):
        body = b'# caf\xc3\xa9\nsource ~/.other\nalias tailmux=other\n# no newline \xce\xa9'
        self.rc.write_bytes(body)
        self.rc.chmod(0o640)
        (self.home / 'aliases').write_text('unchanged')
        p = self.success('install')
        self.assertIn(str(self.prefix / 'tailmux'), p.stdout)
        self.assertIn('may shadow bare tailmux', p.stdout)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual(self.rc.read_bytes(), body)
        self.assertEqual(self.rc.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in self.prefix.iterdir()), ['.tailmux-receipt', 'tailmux'])
        self.success('install')
        p = subprocess.run([str(self.prefix / 'tailmux'), '--version'], env=cli_environment(self.bin, self.env), capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, 'tailmux 0.2.0\n'))
        self.success('uninstall')
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.assertEqual(self.rc.read_bytes(), body)
        self.assertEqual((self.home / 'aliases').read_text(), 'unchanged')
        backups = list(self.prefix.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.success('uninstall')
        self.assertEqual(len(list(self.prefix.glob('.tailmux-backup.*'))), 1)

    def test_installed_absolute_client_resolves_and_connects(self):
        self.success('install')
        trace = self.root / 'client-argv'
        self.script('tailscale', '''#!/bin/bash
case "$1" in
  status) cat "$STATUS_FIXTURE" ;;
  ssh) printf '%s\\0' "$@" > "$CLIENT_TRACE"; exit 37 ;;
  *) exit 97 ;;
esac
''')
        jq = self.bin / 'jq'
        jq.symlink_to(shutil.which('jq'))
        (self.bin / 'head').symlink_to(shutil.which('head'))
        env = dict(self.env, STATUS_FIXTURE=str(FIXTURES / 'status-v1.104.2/running.json'), CLIENT_TRACE=str(trace))
        p = subprocess.run([str(self.prefix / 'tailmux'), 'alice@work'], env=cli_environment(self.bin, env), capture_output=True, text=True)
        self.assertEqual(p.returncode, 37, p.stdout + p.stderr)
        argv = trace.read_bytes().split(b'\0')[:-1]
        self.assertEqual(argv[:3], [b'ssh', b'alice@100.64.0.20', b'-t'])
        self.assertEqual(len(argv), 4)
        self.assertIn(b'tmux attach || tmux new', argv[3])
        self.assertFalse(self.trace.exists())
        self.success('uninstall')

    def test_census_and_functions_preserved_without_evaluation(self):
        for form in CENSUS + ['# opaque \x00 bytes\n', 'tailmux() { echo user; }\n', 'function tailmux { :; }\n']:
            body = (form + 'touch "$HOME/RC_WAS_EXECUTED"\nsource "$HOME/unknown-code"\n').encode()
            self.rc.write_bytes(body)
            self.success('install')
            self.assertEqual(self.rc.read_bytes(), body)
            self.assertFalse((self.home / 'RC_WAS_EXECUTED').exists())
            p = subprocess.run([str(self.prefix / 'tailmux'), '--version'], env=cli_environment(self.bin, self.env), capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout), (0, 'tailmux 0.2.0\n'))
            self.success('uninstall')
            self.assertEqual(self.rc.read_bytes(), body)

    def test_all_known_blocks_and_missing_final_newline(self):
        for fixture in sorted(FIXTURES.glob('legacy-*.rc')):
            with self.subTest(fixture=fixture.name):
                before = b'# prefix caf\xc3\xa9\n'
                after = b'# suffix \xce\xa9 without newline'
                original = before + fixture.read_bytes() + after
                self.rc.write_bytes(original)
                self.rc.chmod(0o640)
                p = self.success('install')
                self.assertIn('Recognized managed blocks removed', p.stdout)
                self.assertEqual(self.rc.read_bytes(), before + after)
                self.assertEqual(self.rc.stat().st_mode & 0o777, 0o640)
                backups = list(self.home.glob('.tailmux-backup.*/original'))
                self.assertTrue(any(b.read_bytes() == original for b in backups))
                self.success('uninstall')
                self.assertEqual(self.rc.read_bytes(), before + after)
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        drive = (FIXTURES / 'legacy-taildrive-mount-pr01.rc').read_bytes()
        self.rc.write_bytes(b'# one\n' + core + b'# two\n' + drive + b'# end')
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'# one\n# two\n# end')
        self.success('uninstall')
        self.rc.write_bytes(core.rstrip(b'\n'))
        self.success('uninstall')
        self.assertEqual(self.rc.read_bytes(), b'')

    def test_unknown_changed_and_multifile_refuse_before_writes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        for body in [core.replace(b'tmux attach', b'tmux attach-CHANGED'), core.replace(b'(tailmux)', b'(unknown)'),
                     core + core, core.split(b'# <<<')[0], b'# <<< tailmux managed block (tailmux) <<<\n',
                     core.replace(b'(tailmux) <<<', b'(taildrive) <<<')]:
            self.rc.write_bytes(core)
            (self.home / '.bashrc').write_bytes(body)
            before = self.tree()
            for operation in ('install', 'uninstall'):
                self.refusal(operation)
                self.assertEqual(self.rc.read_bytes(), core)
                self.assertEqual((self.home / '.bashrc').read_bytes(), body)
                self.assertEqual(self.tree(), before)

    def test_symlink_and_foreign_installation_refusals(self):
        self.prefix.mkdir(parents=True)
        binary = self.prefix / 'tailmux'
        binary.write_text('foreign')
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='receipt is missing')
            self.assertEqual(binary.read_text(), 'foreign')
        binary.unlink()
        target = self.root / 'target'
        target.write_text('# unrelated')
        self.rc.symlink_to(target)
        self.success('install')
        self.success('uninstall')
        self.assertTrue(self.rc.is_symlink())
        target.write_bytes((FIXTURES / 'legacy-core-pr01.rc').read_bytes())
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='Symlinked RC paths')
            self.assertTrue(self.rc.is_symlink())
        self.rc.unlink()
        binary.symlink_to(target)
        self.refusal('install')
        self.assertTrue(binary.is_symlink())

    def test_modified_executable_and_receipt_refuse(self):
        self.success('install')
        binary = self.prefix / 'tailmux'
        original = binary.read_bytes()
        binary.write_bytes(original + b'\n: modified\n')
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='modified installation')
        binary.write_bytes(original)
        receipt = self.prefix / '.tailmux-receipt'
        receipt.write_text('foreign\n')
        self.refusal('uninstall')
        receipt.unlink()
        receipt.symlink_to(self.root / 'absent')
        self.refusal('install')

    def test_interrupted_publication_and_false_success(self):
        real_mv = shutil.which('mv')
        self.script('mv', '#!/bin/bash\n[[ "$1" != *tailmux-stage*/tailmux ]] || exit 73\nexec "' + real_mv + '" "$@"\n')
        self.refusal('install')
        self.assertTrue((self.prefix / '.tailmux-receipt').exists())
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.script('mv', '#!/bin/bash\nexec "' + real_mv + '" "$@"\n')
        self.success('install')
        self.success('uninstall')
        self.script('mv', '#!/bin/bash\nexit 0\n')
        self.refusal('install', contains='Published receipt verification failed')
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.assertFalse((self.prefix / '.tailmux-receipt').exists())

    def test_actual_interruption_retains_receipt_and_recovers(self):
        ready = self.root / 'publisher-ready'
        real_mv = shutil.which('mv')
        self.script('mv', '''#!/bin/bash
if [[ "$1" == *tailmux-stage*/tailmux ]]; then
  : > "$PUBLISHER_READY"
  exec /bin/sleep 30
fi
exec "''' + real_mv + '''" "$@"
''')
        env = dict(self.env, PUBLISHER_READY=str(ready))
        p = subprocess.Popen(['/bin/bash', str(SETUP), 'install'], env=cli_environment(self.bin, env),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            for _ in range(300):
                if ready.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            os.killpg(p.pid, signal.SIGTERM)
            stdout, _ = p.communicate(timeout=5)
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn(b'Client installed at', stdout)
            self.assertTrue((self.prefix / '.tailmux-receipt').exists())
            self.assertFalse((self.prefix / 'tailmux').exists())
            self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate()
        (self.bin / 'mv').unlink()
        (self.bin / 'mv').symlink_to(real_mv)
        self.success('install')
        self.success('uninstall')

    def test_write_failures_and_rc_backup_truth(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for name in ('mktemp', 'cp', 'mv', 'dd'):
            original = shutil.which(name)
            self.script(name, '#!/bin/bash\nexit 73\n')
            self.refusal('install')
            self.assertEqual(self.rc.read_bytes(), core)
            (self.bin / name).unlink()
            (self.bin / name).symlink_to(original)
        self.success('install')
        self.rc.write_bytes(core)
        self.script('mv', '#!/bin/bash\nexit 0\n')
        self.refusal('install', contains='Published RC content or metadata verification failed')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertTrue(any(p.read_bytes() == core for p in self.home.glob('.tailmux-backup.*/original')))

    def test_false_success_removal_and_missing_binary_receipt(self):
        self.success('install')
        real_rm = shutil.which('rm')
        self.script('rm', '#!/bin/bash\nexit 0\n')
        self.refusal('uninstall', contains='Executable removal verification failed')
        self.assertTrue((self.prefix / 'tailmux').exists())
        self.assertTrue((self.prefix / '.tailmux-receipt').exists())
        (self.bin / 'rm').unlink()
        (self.bin / 'rm').symlink_to(real_rm)
        (self.prefix / 'tailmux').unlink()
        self.success('uninstall')
        self.assertFalse((self.prefix / '.tailmux-receipt').exists())

    def test_environment_prefix_spaces_and_all_rc_locations(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for variable in ('HOME', 'ZDOTDIR'):
            for value in ('relative path', str(self.home) + '\n' + str(self.root)):
                for operation in ('install', 'uninstall'):
                    before = self.tree()
                    self.refusal(operation, contains='HOME and ZDOTDIR', **{variable: value})
                    self.assertEqual(self.tree(), before)
                    self.assertEqual(self.rc.read_bytes(), core)
        zsh = self.home / 'zsh space'
        zsh.mkdir()
        for name in ('.bashrc', '.bash_profile'):
            (self.home / name).write_bytes(core)
        (zsh / '.zshrc').write_bytes(core)
        prefix = self.home / 'bin space'
        self.success('install', '--prefix', str(prefix), ZDOTDIR=str(zsh))
        for path in [self.rc, self.home / '.bashrc', self.home / '.bash_profile', zsh / '.zshrc']:
            self.assertEqual(path.read_bytes(), b'')
        self.success('uninstall', '--prefix', str(prefix), ZDOTDIR=str(zsh))
        for invalid in ('', 'relative', '/', str(prefix) + '/../bin', str(prefix) + '\nother'):
            self.refusal('install', '--prefix', invalid)
        home_space = self.root / 'home space'
        home_space.mkdir()
        self.success('install', HOME=str(home_space), ZDOTDIR=str(home_space))
        self.success('uninstall', HOME=str(home_space), ZDOTDIR=str(home_space))

    def test_permissions_hardlinks_and_ancestor_modes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for mode in (0o664, 0o646):
            self.rc.chmod(mode)
            self.refusal('install', contains='writable RC files')
            self.assertEqual(self.rc.read_bytes(), core)
        self.rc.chmod(0o644)
        os.link(self.rc, self.root / 'hardlink')
        self.refusal('install', contains='one hard link')
        (self.root / 'hardlink').unlink()
        self.home.chmod(0o775)
        self.refusal('install', contains='writable non-sticky RC ancestor')
        self.home.chmod(0o755)
        self.rc.chmod(0o444)
        self.refusal('install', contains='RC or parent is not writable')
        self.rc.chmod(0o644)
        self.assertEqual(self.rc.read_bytes(), core)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_legacy_migration_preserves_xattrs_and_backup(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        original = b'# before\n' + core + b'# after without newline'
        self.rc.write_bytes(original)
        self.rc.chmod(0o640)
        os.setxattr(self.rc, 'user.tailmux-test', b'opaque\x00metadata')
        before = self.rc.stat()
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'# before\n# after without newline')
        self.assertEqual(os.getxattr(self.rc, 'user.tailmux-test'), b'opaque\x00metadata')
        after = self.rc.stat()
        self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                         (before.st_uid, before.st_gid, before.st_mode))
        backups = list(self.home.glob('.tailmux-backup.*/original'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(os.getxattr(backups[0], 'user.tailmux-test'), b'opaque\x00metadata')
        self.success('uninstall')
        self.assertEqual(self.rc.read_bytes(), b'# before\n# after without newline')

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_security_context_mode_indicator_is_accepted_but_acls_are_refused(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        os.setxattr(self.rc, 'user.context-sentinel', b'preserved context data')
        real_ls = shutil.which('ls')
        def indicator(suffix):
            self.script('ls', '#!/bin/bash\nlisting="$("' + real_ls + '" "$@")" || exit $?\n'
                        'permissions=${listing%% *}\nif [[ $permissions == -* ]]; then\n'
                        'printf \'%s' + suffix + '%s\\n\' "$permissions" "${listing#"$permissions"}"\n'
                        'else printf \'%s\\n\' "$listing"; fi\n')
        indicator('.')
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'')
        self.assertEqual(os.getxattr(self.rc, 'user.context-sentinel'), b'preserved context data')
        backups = list(self.home.glob('.tailmux-backup.*/original'))
        self.assertEqual(backups[0].read_bytes(), core)
        self.assertEqual(os.getxattr(backups[0], 'user.context-sentinel'), b'preserved context data')
        self.success('uninstall')
        self.rc.write_bytes(core)
        indicator('+')
        before = self.tree()
        self.refusal('install', contains='RC has ACLs or extended metadata')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertEqual(self.tree(), before)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_unverified_inode_flags_refuse_before_lifecycle_writes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for code, message in [("printf '%s\\n' '----i------------- file'", 'Unsupported Linux inode flags'),
                              ('exit 73', 'Cannot verify Linux inode flags')]:
            self.script('lsattr', '#!/bin/bash\n' + code + '\n')
            before = self.tree()
            for action in ('install', 'uninstall'):
                self.refusal(action, contains=message)
                self.assertEqual(self.rc.read_bytes(), core)
                self.assertEqual(self.tree(), before)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_dropped_xattrs_refuse_rc_replacement(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        os.setxattr(self.rc, 'user.tailmux-test', b'preserve me')
        real_cp = shutil.which('cp')
        self.script('cp', '#!/bin/bash\nexec "' + real_cp + '" -p -- "${@: -2}"\n')
        self.refusal('install', contains='RC metadata could not be preserved')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertEqual(os.getxattr(self.rc, 'user.tailmux-test'), b'preserve me')
        self.assertEqual(list(self.home.glob('.tailmux-backup.*/original')), [])

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS metadata evidence only')
    def test_macos_xattrs_flags_and_ancestor_acls(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        subprocess.run(['/usr/bin/xattr', '-w', 'user.tailmux-test', 'sentinel', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        subprocess.run(['/usr/bin/chflags', 'nodump', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        self.addCleanup(subprocess.run, ['/usr/bin/chflags', '0', str(self.rc)], check=False, env=cli_environment(self.bin, self.env))
        flags = self.rc.stat().st_flags
        before = subprocess.check_output(['/usr/bin/xattr', '-lx', str(self.rc)], env=cli_environment(self.bin, self.env))
        self.success('install')
        self.assertEqual(subprocess.check_output(['/usr/bin/xattr', '-lx', str(self.rc)], env=cli_environment(self.bin, self.env)), before)
        self.assertEqual(self.rc.stat().st_flags, flags)
        self.success('uninstall')
        for node in (self.home, self.root):
            subprocess.run(['/usr/bin/xattr', '-w', 'user.tailmux-test', 'acl-marker', str(node)], check=True, env=cli_environment(self.bin, self.env))
            subprocess.run(['/bin/chmod', '+a', 'everyone allow delete_child,add_subdirectory', str(node)], check=True, env=cli_environment(self.bin, self.env))
            self.addCleanup(subprocess.run, ['/bin/chmod', '-N', str(node)], check=False, env=cli_environment(self.bin, self.env))
            for operation in ('install', 'uninstall'):
                self.refusal(operation, contains='Unknown or mutating RC ancestor ACLs')
            subprocess.run(['/bin/chmod', '-N', str(node)], check=True, env=cli_environment(self.bin, self.env))
        for node in (self.home, self.root):
            subprocess.run(['/bin/chmod', '+a', 'everyone deny delete', str(node)], check=True, env=cli_environment(self.bin, self.env))
        before = [subprocess.check_output(['/bin/ls', '-lde', str(n)], env=cli_environment(self.bin, self.env)).split(b'\n')[1:] for n in (self.home, self.root)]
        self.success('install')
        self.success('uninstall')
        after = [subprocess.check_output(['/bin/ls', '-lde', str(n)], env=cli_environment(self.bin, self.env)).split(b'\n')[1:] for n in (self.home, self.root)]
        self.assertEqual(after, before)
        for node in (self.home, self.root):
            subprocess.run(['/bin/chmod', '-N', str(node)], check=True, env=cli_environment(self.bin, self.env))
        self.rc.write_bytes(core)
        subprocess.run(['/bin/chmod', '+a', 'everyone allow read', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        self.addCleanup(subprocess.run, ['/bin/chmod', '-N', str(self.rc)], check=False, env=cli_environment(self.bin, self.env))
        self.refusal('install', contains='RC ACLs are refused')
        self.assertEqual(self.rc.read_bytes(), core)


if __name__ == '__main__':
    unittest.main(verbosity=2)
