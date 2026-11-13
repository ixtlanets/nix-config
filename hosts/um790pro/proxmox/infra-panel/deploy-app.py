#!/usr/bin/env python3
"""Deploy a reviewed local release to our CT105; never print generated credentials."""
import argparse
import base64
import hashlib
import io
import json
import pathlib
import runpy
import shlex
import subprocess
import tarfile

BASE = pathlib.Path(__file__).resolve().parent
SSH = runpy.run_path(str(BASE / 'prepare-host.py'))['SSH']
REMOTE = r'''
import base64,hashlib,json,os,pathlib,pwd,secrets,shlex,socket,subprocess,sys
assert socket.gethostname()=='pve-um790'
os.umask(0o077)
payload=json.load(sys.stdin)
def run(*args,input=None):
 p=subprocess.run(args,input=input,text=True,capture_output=True)
 if p.returncode:
  # Never include command/env/output: future tools may return token material.
  raise RuntimeError('Deployment subprocess failed: '+args[0])
 return p.stdout
def ct(*args,input=None):return run('pct','exec','105','--',*args,input=input)
assert 'hostname: infra-panel\n' in pathlib.Path('/etc/pve/lxc/105.conf').read_text()
run('/usr/local/sbin/infra-panel-network','--verify')
status=json.loads(run('tailscale','status','--json'))
owner=status.get('User',{}).get(str(status['Self']['UserID']),{}).get('LoginName')
assert owner and not any(ord(c)<32 for c in owner),'Missing safe Tailscale owner identity'
assert status['Self']['DNSName'].rstrip('.')=='pve-um790.tailf108.ts.net'
serve=json.loads(run('tailscale','serve','status','--json') or '{}')
existing=(serve.get('TCP') or {}).get('8444')
assert not existing or existing.get('HTTPS') is True,'8444 already has another listener'
# Reject an unrelated HTTP handler on our proposed TLS origin.
web=(serve.get('Web') or {}).get('pve-um790.tailf108.ts.net:8444')
if web:assert web=={'Handlers':{'/':{'Proxy':'http://127.0.0.1:3101'}}},'8444 belongs to another service'
archive=base64.b64decode(payload['archive'])
assert hashlib.sha256(archive).hexdigest()==payload['sha256']
if not payload['apply']:
 print('DRY RUN: CT105, network gate, Serve8444 ownership and release digest verified; no files, tokens or listeners changed');raise SystemExit()
root=pathlib.Path('/etc/infra-panel');root.mkdir(mode=0o700,exist_ok=True)
release=root/('release-'+payload['sha256'][:16]+'.tgz')
if release.exists():assert release.read_bytes()==archive
else:release.write_bytes(archive);release.chmod(0o600)
# Provision a NEW, privilege-separated audit-only identity, never a root token.
user='infra-panel@pve';token='inventory';comment='Infra Panel read-only inventory'
users=json.loads(run('pveum','user','list','--output-format','json'))
found=next((u for u in users if u['userid']==user),None)
if found:assert found.get('comment')==comment,'Unmanaged PVE identity collision'
else:run('pveum','user','add',user,'--comment',comment,'--enable','1')
run('pveum','acl','modify','/','--users',user,'--roles','PVEAuditor')
secretpath=root/'proxmox-token.json'
if secretpath.exists():
 assert not secretpath.is_symlink() and secretpath.stat().st_mode&0o077==0
 credential=json.loads(secretpath.read_text())
else:
 tokens=json.loads(run('pveum','user','token','list',user,'--output-format','json'))
 assert not any(t['tokenid']==token for t in tokens),'Token exists but its stored secret is missing; explicit rotation required'
 credential=json.loads(run('pveum','user','token','add',user,token,'--privsep','1','--comment',comment,'--output-format','json'))
 assert credential['full-tokenid']==user+'!'+token and credential.get('value')
 fd=os.open(secretpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as out:json.dump(credential,out)
run('pveum','acl','modify','/','--tokens',user+'!'+token,'--roles','PVEAuditor')
tokens=json.loads(run('pveum','user','token','list',user,'--output-format','json'))
assert next(t for t in tokens if t['tokenid']==token).get('privsep')==1
# Verify the actual effective privileges; an ACL label alone is not sufficient.
permissions=json.loads(run('pveum','user','token','permissions',user,token,'--path','/','--output-format','json'))
allowed={'Datastore.Audit','Mapping.Audit','Pool.Audit','SDN.Audit','Sys.Audit','Sys.Syslog','VM.Audit','VM.GuestAgent.Audit'}
def privileges(value):
 if isinstance(value,dict):
  result=set()
  for key,item in value.items():
   if '.' in key and isinstance(item,(bool,int)) and item:result.add(key)
   elif isinstance(item,(dict,list)):result.update(privileges(item))
  return result
 if isinstance(value,list):return set().union(*(privileges(item) for item in value))
 return set()
effective=privileges(permissions)
assert {'Sys.Audit','VM.Audit'}<=effective and effective<=allowed,'Effective Proxmox token privileges are not audit-only'
print('Privilege-separated PVEAuditor token and effective read-only permissions: PASS')
run('pct','push','105',str(release),'/opt/infra-panel/downloads/app.tgz','--perms','0600')
# Installer runs before loading secrets; its output is safe, but print only bounded errors.
install=r"""set -euo pipefail
umask 022
export PATH=/opt/infra-panel/node/bin:/usr/sbin:/usr/bin:/sbin:/bin
[ "$(node --version)" = 'v26.13.0' ]
[ "$(pnpm --version)" = '12.4.0' ]
tar -xzf /opt/infra-panel/downloads/app.tgz --strip-components=1 --no-same-owner -C /opt/infra-panel/app
cd /opt/infra-panel/app
npm_config_build_from_source=true npm_config_nodedir=/opt/infra-panel/node pnpm install --prod --frozen-lockfile --reporter append-only
node --import tsx --input-type=module -e 'import Database from "better-sqlite3";const d=new Database(":memory:");if(d.prepare("select 1 as ok").get().ok!==1)process.exit(1);d.close();console.log("Native SQLite: PASS")'
"""
ct('/bin/bash','-s',input=install)
# Existing artifact key and PVE API token are preserved across ordinary re-deploys.
keypath=root/'profile-artifact-key'
if keypath.exists():
 assert not keypath.is_symlink() and keypath.stat().st_mode&0o077==0
 key=keypath.read_text().strip();assert len(key)==64 and bytes.fromhex(key)
else:
 key=secrets.token_hex(32)
 fd=os.open(keypath,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as out:out.write(key+'\n')
endpoint=(root/'proxmox-endpoint').read_text().strip()
origin='https://pve-um790.tailf108.ts.net:8444'
env={'NODE_ENV':'production','HOST':'10.77.8.2','PORT':'3100','DATABASE_PATH':'/var/lib/infra-panel/inventory.sqlite','STATIC_DIR':'/opt/infra-panel/app/dist','TRUSTED_PROXY_IPS':'10.77.8.1','ADMIN_LOGINS':owner,'ALLOWED_HOSTS':'pve-um790.tailf108.ts.net:8444','ALLOWED_ORIGINS':origin,'PROXMOX_ENDPOINT':endpoint,'PROXMOX_TOKEN_ID':credential['full-tokenid'],'PROXMOX_TOKEN_SECRET':credential['value'],'PROXMOX_CLUSTER_ID':'pve-um790','PROXMOX_CONNECT_IP':'10.77.8.1','NODE_EXTRA_CA_CERTS':'/etc/infra-panel/pve-ca.pem','PROFILE_ARTIFACT_DIR':'/var/lib/infra-panel/profiles','PROFILE_ARTIFACT_KEY':key,'CHECK_ALLOWED_HOSTS':'100.95.213.117,100.116.87.104,personal-openclaw.tailf108.ts.net,pve.nikcode.xyz','CHECK_ALLOWED_PRIVATE_IPS':'100.95.213.117,100.116.87.104,100.99.139.46'}
def quote(value):
 assert not any(c in value for c in '\n\r\x00')
 return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
envtext='\n'.join(name+'='+quote(value) for name,value in env.items())+'\n'
ct('python3','-c',"import os,pathlib,sys;p=pathlib.Path('/etc/infra-panel/app.env');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600);f=os.fdopen(fd,'w');f.write(sys.stdin.read());f.close()",input=envtext)
ct('python3','-c',"import pathlib,sys;p=pathlib.Path('/etc/systemd/system/infra-panel.service');p.write_text(sys.stdin.read());p.chmod(0o644)",input=payload['files']['infra-panel.service'])
ct('systemctl','daemon-reload');ct('systemctl','enable','--now','infra-panel.service');ct('systemctl','restart','infra-panel.service')
for name in ['infra-panel-proxy.socket','infra-panel-proxy.service']:
 path=pathlib.Path('/etc/systemd/system')/name
 if path.exists():assert path.read_text()==payload['files'][name],'Unmanaged proxy unit collision'
 else:path.write_text(payload['files'][name]);path.chmod(0o644)
assert pathlib.Path('/usr/lib/systemd/systemd-socket-proxyd').is_file()
run('systemctl','daemon-reload');run('systemctl','enable','--now','infra-panel-proxy.socket')
# HTTP reverse proxy mode injects verified Tailscale identity; raw TCP/TLS mode would not.
run('tailscale','serve','--bg','--https=8444','http://127.0.0.1:3101')
print('CT105 service and root-only-loopback HTTP Serve8444 configured; no dev authentication bypass')
print('Private URL: '+origin)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=pathlib.Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    archive=args.archive.resolve();data=archive.read_bytes()
    assert len(data)<4*1024*1024,'Unexpected release size'
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as package:
        members=package.getmembers()
        assert members and all(m.name.startswith('package/') and '..' not in pathlib.PurePosixPath(m.name).parts and (m.isfile() or m.isdir()) for m in members),'Unsafe release layout'
        names={m.name for m in members}
        assert {'package/server/main.ts','package/server/migrations/0001_initial.sql','package/profiles/store.ts','package/dist/index.html','package/pnpm-lock.yaml','package/pnpm-workspace.yaml'}<=names
        assert not any('/.env' in n or n.endswith(('.sqlite','.db','.pem','.key')) for n in names),'Private files in release'
    payload={'apply':args.apply,'archive':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest(),'files':{name:(BASE/name).read_text() for name in ['infra-panel.service','infra-panel-proxy.socket','infra-panel-proxy.service']}}
    result = subprocess.run(SSH+['python3','-c',shlex.quote(REMOTE)],input=json.dumps(payload),text=True)
    if result.returncode: raise SystemExit('Deployment failed; app/ingress acceptance has NOT been completed')
if __name__=='__main__':main()
