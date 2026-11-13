#!/usr/bin/env python3
"""Install pinned Node/pnpm and public PVE CA into OUR already isolated CT105."""
import pathlib
import runpy
import shlex
import subprocess

SSH = runpy.run_path(str(pathlib.Path(__file__).with_name('prepare-host.py')))['SSH']
REMOTE = r'''
import json,pathlib,socket,ssl,subprocess
assert socket.gethostname()=='pve-um790'
assert 'hostname: infra-panel\n' in pathlib.Path('/etc/pve/lxc/105.conf').read_text()
assert subprocess.run(['/usr/local/sbin/infra-panel-network','--verify'],check=True).returncode==0
script=r"""set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::ForceIPv4=true update
apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends ca-certificates curl xz-utils python3 make g++ openssl
if ! id infra-panel >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /var/lib/infra-panel --shell /usr/sbin/nologin infra-panel
fi
install -d -m 755 /opt/infra-panel /opt/infra-panel/node /opt/infra-panel/app
install -d -m 700 /opt/infra-panel/downloads
# Runtime must traverse this directory to read the PUBLIC CA; app.env stays root0600.
install -d -m 750 -o root -g infra-panel /etc/infra-panel
install -d -m 700 -o infra-panel -g infra-panel /var/lib/infra-panel
version=v26.13.0
archive=node-${version}-linux-x64.tar.xz
if [ ! -x /opt/infra-panel/node/bin/node ]; then
  cd /opt/infra-panel/downloads
  curl --fail --silent --show-error --ipv4 --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 180 -o SHASUMS256.txt https://nodejs.org/dist/${version}/SHASUMS256.txt
  curl --fail --silent --show-error --ipv4 --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 300 -o "$archive" https://nodejs.org/dist/${version}/${archive}
  python3 - "$archive" <<'VERIFY'
import hashlib,pathlib,sys
name=sys.argv[1]
matching=[line.split() for line in pathlib.Path('SHASUMS256.txt').read_text().splitlines() if line.split()[-1]==name]
assert len(matching)==1,'missing or duplicate official checksum'
assert hashlib.file_digest(pathlib.Path(name).open('rb'),'sha256').hexdigest()==matching[0][0],'Node checksum mismatch'
print('Official pinned Node archive checksum: PASS')
VERIFY
  tar -xJf "$archive" --strip-components=1 --no-same-owner -C /opt/infra-panel/node
fi
export PATH=/opt/infra-panel/node/bin:/usr/sbin:/usr/bin:/sbin:/bin
[ "$(node --version)" = "$version" ]
if [ ! -x /opt/infra-panel/node/bin/pnpm ]; then
  npm install --global --prefix /opt/infra-panel/node --ignore-scripts pnpm@12.4.0
fi
[ "$(pnpm --version)" = '12.4.0' ]
# Use node-gyp already shipped in the checksum-verified Node distribution;
# no separate network installer and no system Node replacement are needed.
if [ ! -e /opt/infra-panel/node/bin/node-gyp ]; then
  ln -s ../lib/node_modules/npm/node_modules/node-gyp/bin/node-gyp.js /opt/infra-panel/node/bin/node-gyp
fi
[ "$(node-gyp --version)" = 'v12.4.0' ]
node --version; pnpm --version; node-gyp --version
"""
p=subprocess.run(['pct','exec','105','--','/bin/bash','-s'],input=script,text=True,capture_output=True)
if p.returncode:
 print(p.stdout[-4000:]);print(p.stderr[-4000:]);raise SystemExit(p.returncode)
print('CT105 pinned Node26.13.0/pnpm12.4.0/build prerequisites: PASS')
ca=pathlib.Path('/etc/pve/pve-root-ca.pem').read_text()
subprocess.run(['pct','exec','105','--','python3','-c',"import pathlib,sys;p=pathlib.Path('/etc/infra-panel/pve-ca.pem');p.write_bytes(sys.stdin.buffer.read());p.chmod(0o644)"],input=ca,text=True,check=True)
# CT105 is deliberately NOT a tailnet node and uses public DNS. Pin the one
# authorized tailnet hostname locally, retaining its TLS hostname/SNI.
private_host=r"""import pathlib,stat
p=pathlib.Path('/etc/hosts');s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
hostname='personal-openclaw.tailf108.ts.net';address='100.116.87.104'
records=[line.split('#',1)[0].split() for line in p.read_text().splitlines()]
matching=[r for r in records if hostname in r[1:]]
assert all(r[0]==address for r in matching),'Conflicting authorized private hostname'
if not matching:
 with p.open('a') as out:out.write('\n# Infra Panel: explicit authorized tailnet endpoint (public DNS cannot resolve MagicDNS)\n'+address+' '+hostname+'\n')
"""
subprocess.run(['pct','exec','105','--','python3','-c',private_host],check=True)
context=ssl.create_default_context();context.load_verify_locations(cadata=ca)
selected=None
for name in ['pve.nikcode.xyz','pve-um790','pve-um790.local']:
 try:
  with socket.create_connection(('127.0.0.1',8006),timeout=5) as raw:
   with context.wrap_socket(raw,server_hostname=name):selected=name
  break
 except ssl.SSLCertVerificationError:pass
assert selected,'PVE API certificate matches no authorized endpoint name'
pathlib.Path('/etc/infra-panel/proxmox-endpoint').write_text('https://'+selected+':8006\n')
print('Verified PVE API TLS hostname with system/cluster CA:',selected)
'''
subprocess.run(SSH+['python3','-c',shlex.quote(REMOTE)],check=True)
