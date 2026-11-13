#!/usr/bin/env python3
"""Prepare the explicitly authorized dedicated LXC. Never touch existing guests.
Dry-run by default. --apply creates only managed assets, bridge and CT105.
Run locally from the owner's workstation; SSH target and key are pinned.
"""
import argparse
import base64
import json
import pathlib
import shlex
import subprocess

BASE = pathlib.Path(__file__).resolve().parent
SSH = ['ssh', '-F', '/dev/null', '-i', '/home/nik/migration/pve-kingston-install-2026-11-06/id_ed25519',
       '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'HostKeyAlias=pve-um790-native', '-o', 'UserKnownHostsFile=/home/nik/migration/pve-kingston-install-2026-11-06/known_hosts', 'root@192.168.1.241']
FILES = {
 'infra-panel-network': ('/usr/local/sbin/infra-panel-network', 0o755),
 'infra-panel-network.nft': ('/etc/infra-panel/network.nft', 0o600),
 'infra-panel-network.service': ('/etc/systemd/system/infra-panel-network.service', 0o644),
 'infra-panel.interfaces': ('/etc/network/interfaces.d/infra-panel', 0o644),
 'infra-panel-hook.py': ('/var/lib/vz/snippets/infra-panel-hook.py', 0o755),
}
REMOTE = r'''
import base64,hashlib,json,os,pathlib,pwd,socket,subprocess,sys
assert socket.gethostname()=='pve-um790','wrong host'
payload=json.load(sys.stdin)
def run(*args):return subprocess.run(args,check=True,text=True,capture_output=True).stdout
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k not in ('handle','metainfo','counter')}
 if isinstance(x,list):return [clean(v) for v in x if not isinstance(v,dict) or 'metainfo' not in v]
 return x
def baseline():
 data=[clean(json.loads(run('nft','-j','list','table','inet',t))) for t in ['pve_guest_vpn','pve_home']]
 data+=[json.loads(run('ip','-j','-4','rule','show')),json.loads(run('ip','-j','-4','route','show','table','18077'))]
 return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
def gates():
 for vmid in ['102','103']:
  run('python3','/root/audiobook-contour-migration-20261107/boot-gate/validate.py',vmid)
vm=pathlib.Path('/etc/pve/qemu-server/105.conf')
ct=pathlib.Path('/etc/pve/lxc/105.conf')
assert not vm.exists(),'VMID105 occupied by a VM'
assert not ct.exists() or 'hostname: infra-panel\n' in ct.read_text(),'CT105 not owned by this deployment'
assert 'source /etc/network/interfaces.d/*' in pathlib.Path('/etc/network/interfaces').read_text(),'network snippets not enabled'
assert pathlib.Path('/var/lib/vz/template/cache/debian-13-standard_13.6-1_amd64.tar.zst').is_file(),'expected cached Debian template missing'
gates(); before=baseline()
print('Existing VM102/103 gates: PASS; current protected network fingerprint:',before)
for item in payload['files']:
 p=pathlib.Path(item['path']);content=base64.b64decode(item['content'])
 assert not p.exists() or p.read_bytes()==content, 'refuse overwriting changed managed asset: '+str(p)
if not payload['apply']:
 print('DRY RUN: dedicated vmbr2 10.77.8.1/24; unprivileged CT105 infra-panel 10.77.8.2, 2 cores/1536MiB/8GiB; no existing guest changes')
 sys.exit(0)
try: user=pwd.getpwnam('infra-panel-proxy')
except KeyError:
 run('useradd','--system','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin','infra-panel-proxy')
 user=pwd.getpwnam('infra-panel-proxy')
assert user.pw_uid>0 and user.pw_shell=='/usr/sbin/nologin','unexpected proxy account'
pathlib.Path('/etc/infra-panel').mkdir(mode=0o700,exist_ok=True)
for item in payload['files']:
 p=pathlib.Path(item['path']);content=base64.b64decode(item['content'])
 p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,item['mode'])
  with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
 os.chmod(p,item['mode'])
run('nft','-c','-f','/etc/infra-panel/network.nft')
run('systemctl','daemon-reload')
run('systemctl','enable','--now','infra-panel-network.service')
run('/usr/local/sbin/infra-panel-network','--verify')
new=not ct.exists()
if new:
 run('pct','create','105','local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst',
     '--hostname','infra-panel','--unprivileged','1','--cores','2','--memory','1536','--swap','512',
     '--rootfs','local-lvm:8','--net0','name=eth0,bridge=vmbr2,firewall=0,gw=10.77.8.1,ip=10.77.8.2/24,type=veth',
     '--nameserver','1.1.1.1','--onboot','1','--startup','order=50,up=10,down=30',
     '--hookscript','local:snippets/infra-panel-hook.py',
     '--description','Infra Panel: private read-only inventory/monitoring; dedicated isolated bridge. Managed by nix-config.')
 # Actual negative boot acceptance on OUR stopped CT only. Do not flush rules.
 stamp=pathlib.Path('/run/infra-panel-network.json');original=stamp.read_bytes()
 try:
  stamp.write_text('{}\n')
  failed=subprocess.run(['pct','start','105'],text=True,capture_output=True)
  assert failed.returncode!=0,'CT105 started with invalid network evidence'
  assert run('pct','status','105').strip()=='status: stopped','CT105 must remain stopped'
  print('CT105 invalid-network startup refusal: PASS')
 finally:stamp.write_bytes(original);os.chmod(stamp,0o600)
if run('pct','status','105').strip()=='status: stopped':run('pct','start','105')
run('/usr/local/sbin/infra-panel-network','--verify')
gates();after=baseline();assert before==after,'existing protected rules/routes changed unexpectedly'
print('CT105 running; existing VM102/103 gates and protected network fingerprint unchanged: PASS')
print('Resources: 2 cores, 1536MiB RAM, 512MiB swap, 8GiB rootfs; native monitor egress is NOT the protected guest VPN')
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    payload={'apply':args.apply,'files':[{'path':target,'mode':mode,'content':base64.b64encode((BASE/source).read_bytes()).decode()} for source,(target,mode) in FILES.items()]}
    subprocess.run(SSH+['python3','-c',shlex.quote(REMOTE)],input=json.dumps(payload),text=True,check=True)

if __name__=='__main__': main()
