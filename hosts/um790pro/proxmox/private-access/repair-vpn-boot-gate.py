#!/usr/bin/env python3
"""One-shot, hash-pinned repair of the physical PVE read-only VM boot gate.

Run --check (default) on pve-um790 before --apply. Tests mutate in-memory live
snapshots, never routing/firewall/guest state. Deployment backs up the original
and atomically replaces only validate.py. The exact nft guard is NOT changed.
"""
import argparse
import contextlib
import copy
import hashlib
import io
import os
import socket
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path

TARGET = Path('/root/audiobook-contour-migration-20261107/boot-gate/validate.py')
BASE_SHA256 = '917f00f5aeb409001f97985d43289159c9a9f4f0ab776fa1e74f403a7a08bc82'
HELPER = '''# Tailscale's marked rules CAN match forwarded traffic. This exception is
# safe only together with the exact nft guard already checked by validate():
# public guest forwarding to any interface except pvegtun is rejected, even
# if a packet carries Tailscale's bypass mark. Never treat these as local-only.
TAILSCALE_RULES = [
 {'priority':5210,'src':'all','fwmark':'0x80000','fwmask':'0xff0000','table':'main'},
 {'priority':5230,'src':'all','fwmark':'0x80000','fwmask':'0xff0000','table':'default'},
 {'priority':5250,'src':'all','fwmark':'0x80000','fwmask':'0xff0000','action':'unreachable'},
 {'priority':5270,'src':'all','table':'52'},
]
def validate_tailscale(rules):
 selected=[r for r in rules if r.get('priority') in (5210,5230,5250,5270)]
 if not selected:return []
 assert sorted(selected,key=lambda r:r['priority'])==TAILSCALE_RULES,'unexpected Tailscale policy rules'
 routes=get(['ip','-j','route','show','table','52'])
 assert len(routes)==len({json.dumps(r,sort_keys=True) for r in routes}),'duplicate Tailscale route'
 for r in routes:
  assert set(r)<= {'dst','dev','flags','scope','type'},'unexpected Tailscale route attributes'
  assert r.get('dev')=='tailscale0' and r.get('flags')==[],'unexpected Tailscale route device or flags'
  assert r.get('scope','link')=='link' and r.get('type','unicast')=='unicast','unexpected Tailscale route action'
  dst=r.get('dst')
  assert dst and dst!='default','Tailscale default route forbidden'
  network=ipaddress.ip_network(dst,strict=True)
  assert network.version==4 and network.subnet_of(ipaddress.ip_network('100.64.0.0/10')),'non-tailnet route in Tailscale table'
 return selected
'''


def candidate(source):
    assert hashlib.sha256(source.encode()).hexdigest() == BASE_SHA256, 'unexpected deployed gate hash; review before patching'
    replacements = [
        ('def validate(vmid):', HELPER + 'def validate(vmid):'),
        (" rules=get(['ip','-j','rule','show'])", " rules=get(['ip','-j','rule','show'])\n tailscale_rules=validate_tailscale(rules)"),
        ("  if p==0 and r.get('table')=='local':continue", "  if p==0 and r.get('table')=='local':continue\n  if r in tailscale_rules:continue"),
    ]
    for old, new in replacements:
        assert source.count(old) == 1, 'patch anchor changed'
        source = source.replace(old, new)
    compile(source, str(TARGET), 'exec')
    return source


def load(source):
    module = types.ModuleType('gate_under_test')
    module.__file__ = str(TARGET)
    exec(compile(source, str(TARGET), 'exec'), module.__dict__)
    return module


def regression_tests(original, updated):
    old, gate = load(original), load(updated)
    rules_key = ('ip', '-j', 'rule', 'show')
    routes_key = ('ip', '-j', 'route', 'show', 'table', '18077')
    ts_key = ('ip', '-j', 'route', 'show', 'table', '52')
    nft_key = ('nft', '-j', 'list', 'table', 'inet', 'pve_guest_vpn')
    snapshot = {key: gate.get(list(key)) for key in (rules_key, routes_key, ts_key, nft_key)}
    checks = 0

    def check(name, mutate=None, allowed=False, module=gate):
        nonlocal checks
        data = copy.deepcopy(snapshot)
        if mutate:
            mutate(data)
        module.get = lambda args: copy.deepcopy(data[tuple(args)])
        for vmid in (102, 103, 104):
            passed = True
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    module.validate(vmid)
            except (AssertionError, ValueError):
                passed = False
            assert passed == allowed, f'{name}: VM{vmid} unexpected acceptance={passed}'
            checks += 1

    def mutate_ts_rule(data, priority, key, value):
        rule = next(r for r in data[rules_key] if r.get('priority') == priority)
        if value is None:
            rule.pop(key, None)
        else:
            rule[key] = value

    check('original reproduces current refusal', module=old)
    check('current live state', allowed=True)
    check('no Tailscale rules', lambda d: d.__setitem__(rules_key, [r for r in d[rules_key] if r.get('priority') not in (5210, 5230, 5250, 5270)]), allowed=True)
    check('empty table52', lambda d: d.__setitem__(ts_key, []), allowed=True)
    check('tailnet peer route', lambda d: d[ts_key].append({'dst': '100.80.1.2', 'dev': 'tailscale0', 'flags': []}), allowed=True)
    check('tailnet prefix', lambda d: d[ts_key].append({'dst': '100.64.0.0/10', 'dev': 'tailscale0', 'flags': [], 'scope': 'link'}), allowed=True)
    for priority in (5210, 5230, 5250, 5270):
        check(f'missing TS rule {priority}', lambda d, p=priority: d.__setitem__(rules_key, [r for r in d[rules_key] if r.get('priority') != p]))
        check(f'duplicate TS rule {priority}', lambda d, p=priority: d[rules_key].append(copy.deepcopy(next(r for r in d[rules_key] if r.get('priority') == p))))
        for key, value in [('src', '10.77.6.103'), ('iif', 'vmbr0'), ('not', True), ('priority', priority - 1)]:
            check(f'changed TS selector {priority}/{key}', lambda d, p=priority, k=key, v=value: mutate_ts_rule(d, p, k, v))
    for key, value in [('fwmark', None), ('fwmark', '0x0'), ('fwmask', '0x0'), ('table', '52')]:
        check('changed mark rule/' + key + str(value), lambda d, k=key, v=value: mutate_ts_rule(d, 5210, k, v))
    check('changed unmarked table', lambda d: mutate_ts_rule(d, 5270, 'table', 'main'))
    for route in [
        {'dst': 'default', 'dev': 'tailscale0', 'flags': []},
        {'dst': '1.1.1.1', 'dev': 'tailscale0', 'flags': []},
        {'dst': '10.0.0.0/8', 'dev': 'tailscale0', 'flags': []},
        {'dst': '100.100.100.100', 'dev': 'pvewifi0', 'flags': []},
        {'dst': '100.100.100.100', 'dev': 'tailscale0', 'flags': ['onlink']},
        {'dst': '100.100.100.100', 'dev': 'tailscale0', 'flags': [], 'gateway': '192.168.1.1'},
        {'dst': '100.100.100.100', 'dev': 'tailscale0', 'flags': [], 'nhid': 1},
        {'dst': '100.100.100.100', 'dev': 'tailscale0', 'flags': [], 'type': 'local'},
        {'dst': '100.100.100.100', 'dev': 'tailscale0', 'flags': [], 'scope': 'host'},
    ]:
        check('unsafe table52/' + str(route), lambda d, r=route: d[ts_key].append(r))
    check('duplicate table52 route', lambda d: d[ts_key].append(copy.deepcopy(d[ts_key][0])))
    check('nft drift', lambda d: d.__setitem__(nft_key, {}))
    check('missing fallback', lambda d: d.__setitem__(routes_key, [r for r in d[routes_key] if r.get('type') != 'unreachable']))
    check('guest bypass default', lambda d: d[routes_key].append({'dst': 'default', 'dev': 'pvewifi0', 'flags': []}))
    check('missing guest rules', lambda d: d.__setitem__(rules_key, [r for r in d[rules_key] if r.get('priority') not in (18085, 18095, 18105)]))
    check('extra early main rule', lambda d: d[rules_key].append({'priority': 5200, 'src': 'all', 'table': 'main'}))
    check('AWG no oif', lambda d: next(r for r in d[rules_key] if r.get('priority') == 18076).pop('oif'))
    check('AWG changed oif', lambda d: next(r for r in d[rules_key] if r.get('priority') == 18076).__setitem__('oif', 'pvewifi0'))
    print(f'PASS: {checks} checks; original refusal reproduced, live candidate accepted, dangerous mutations refused')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    assert socket.gethostname() == 'pve-um790', 'run only on physical pve-um790'
    source = TARGET.read_text()
    updated = candidate(source)
    regression_tests(source, updated)
    if not args.apply:
        print('Check only; no files or live state changed')
        return
    assert os.geteuid() == 0
    assert TARGET.resolve() == TARGET and not TARGET.is_symlink()
    assert TARGET.read_text() == source, 'gate changed while testing'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = TARGET.with_name(TARGET.name + '.before-tailscale-repair-' + stamp)
    with backup.open('xb') as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(source.encode())
        f.flush()
        os.fsync(f.fileno())
    directory_fd = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
        mode = TARGET.stat().st_mode & 0o777

        def replace_durably(text):
            fd, staging = tempfile.mkstemp(prefix='.validate-tailscale-', dir=TARGET.parent)
            with os.fdopen(fd, 'w') as f:
                os.fchmod(f.fileno(), mode)
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(staging, TARGET)
            os.fsync(directory_fd)

        replace_durably(updated)
        try:
            for vmid in (102, 103, 104):
                load(TARGET.read_text()).validate(vmid)
        except Exception:
            replace_durably(source)
            print('Post-install validation failed; original gate restored')
            raise
    finally:
        os.close(directory_fd)
    print('Backup:', backup)
    print('Installed SHA256:', hashlib.sha256(TARGET.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
