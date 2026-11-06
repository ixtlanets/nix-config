#!/usr/bin/env python3
"""Keep system DNS inside the active sing-box TUN; tailnet split DNS wins."""
import subprocess
import time


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True)


def main():
    interface = 'nekoray-tun'
    # sing-box registers its resolved link asynchronously after creating TUN.
    for _ in range(50):
        result = run('resolvectl', 'dns', interface, check=False)
        if result.returncode == 0 and '198.19.0.2' in result.stdout:
            break
        time.sleep(0.1)
    run('resolvectl', 'dns', interface, '198.19.0.2')
    run('resolvectl', 'domain', interface, '~.')
    run('resolvectl', 'dnsovertls', interface, 'no')
    run('resolvectl', 'default-route', interface, 'yes')
    run('resolvectl', 'flush-caches')


if __name__ == '__main__':
    main()
