import shutil


def cli_environment(fake_bin, base, *, allow_missing_tailscale=False, **changes):
    env = dict(base, **changes)
    private = str(fake_bin)
    if env['PATH'].split(':')[0] != private:
        env['PATH'] = private + ':' + env['PATH']
    resolved = shutil.which('tailscale', path=env['PATH'])
    if resolved is None and allow_missing_tailscale:
        return env
    if resolved != str(fake_bin / 'tailscale'):
        raise AssertionError('CLI fixture refused a non-private tailscale executable')
    return env
