#!/usr/bin/env bash
# Optional parent-run Moscow hardening, separate from application deployment.
set -Eeuo pipefail
umask 077
readonly address=132.243.191.232
readonly ssh_dropin=/etc/ssh/sshd_config.d/00-moscow1-key-only.conf
readonly firewall_dir=/etc/moscow1-hardening
readonly firewall_unit=/etc/systemd/system/moscow1-firewall.service
fail() { echo "$1" >&2; exit 1; }
[[ $EUID == 0 ]] || fail 'Run on Moscow as root.'
ip -4 -o addr show scope global | awk '{split($4,a,"/"); print a[1]}' | grep -Fxq "$address" || fail 'Wrong host.'
. /etc/os-release
[[ $ID == ubuntu ]] || fail 'Ubuntu required.'
[[ $# -ge 2 ]] || fail 'Usage: harden.sh apply|rollback BACKUP | confirm BACKUP --verified-independent-root-key-session'
mode=$1; backup=$2
[[ $backup =~ ^/var/backups/moscow1-hardening/[a-zA-Z0-9_-]+$ && ! -L /var/backups &&
   ! -L /var/backups/moscow1-hardening && ! -L $backup ]] || fail 'Invalid backup path.'
readonly timer="moscow1-hardening-rollback-${backup##*/}"

restore() {
  [[ -f $backup/ready && $(cat "$backup/ready") == "$address" ]] || return 1
  local bad=0
  # Only these owned paths/table/unit are changed; never restore the global ruleset.
  if [[ $(systemctl show -p LoadState --value moscow1-firewall.service) != not-found ]]; then
    systemctl disable --now moscow1-firewall.service >>"$backup/rollback.log" 2>&1 || bad=1
  fi
  if nft list table inet moscow1_guard >/dev/null 2>&1; then
    nft delete table inet moscow1_guard >>"$backup/rollback.log" 2>&1 || bad=1
  fi
  rm -f -- "$firewall_unit" "$ssh_dropin" || bad=1
  rm -rf -- "$firewall_dir" || bad=1
  systemctl daemon-reload >>"$backup/rollback.log" 2>&1 || bad=1
  /usr/sbin/sshd -t >>"$backup/rollback.log" 2>&1 &&
    systemctl reload ssh.service >>"$backup/rollback.log" 2>&1 || bad=1
  # Stop only the timer, not this possibly running rollback service itself.
  if [[ $bad == 0 ]]; then
    systemctl stop "$timer.timer" >>"$backup/rollback.log" 2>&1 || bad=1
  fi
  return "$bad"
}
verify_ssh() {
  local effective
  /usr/sbin/sshd -t
  effective=$(/usr/sbin/sshd -T -C "user=root,host=$peer,addr=$peer,laddr=$address,lport=22")
  for option in 'pubkeyauthentication yes' 'passwordauthentication no' \
    'kbdinteractiveauthentication no' 'permitrootlogin prohibit-password' 'authenticationmethods publickey'; do
    # OpenSSH may print the synonymous without-password spelling.
    if [[ $option == 'permitrootlogin prohibit-password' ]]; then
      [[ $effective == *'permitrootlogin without-password'* || $effective == *"$option"* ]] || return 1
    else
      grep -Fxq "$option" <<<"$effective" || return 1
    fi
  done
}

case "$mode" in
  rollback)
    [[ $# == 2 ]] || fail 'Wrong argument count.'
    restore || fail 'Hardening rollback incomplete; inspect private snapshot.'
    echo 'Owned hardening removed; prior SSH files and unrelated firewall rules preserved.'
    exit 0 ;;
  confirm)
    [[ $# == 3 && $3 == --verified-independent-root-key-session ]] || fail 'Independent root key-session verification is required.'
    [[ -f $backup/ready && $(cat "$backup/ready") == "$address" && -f $backup/applied ]] || fail 'No completed hardening transaction.'
    [[ -n ${SSH_CONNECTION:-} && $SSH_CONNECTION != "$(cat "$backup/initial-connection")" ]] || fail 'Confirm from a new independent SSH connection.'
    read -r peer peer_port local_ip local_port <<<"$SSH_CONNECTION"
    [[ $local_ip == "$address" && $local_port == 22 ]] || fail 'Unexpected SSH connection.'
    verify_ssh >"$backup/ssh-confirm.log" 2>&1 || fail 'Effective key-only SSH verification failed.'
    systemctl is-active --quiet moscow1-firewall.service || fail 'Owned firewall unit is not active.'
    nft list table inet moscow1_guard >"$backup/firewall-confirm.nft"
    systemctl stop "$timer.timer"
    touch "$backup/confirmed"
    echo 'Rollback timer cancelled after independent root key-session confirmation.'
    exit 0 ;;
  apply) [[ $# == 2 ]] || fail 'Wrong argument count.' ;;
  *) fail 'Unknown mode.' ;;
esac
[[ -n ${SSH_CONNECTION:-} ]] || fail 'Apply from the existing SSH session; keep it open.'
read -r peer peer_port local_ip local_port <<<"$SSH_CONNECTION"
[[ $local_ip == "$address" && $local_port == 22 ]] || fail 'Only the expected port-22 SSH session is supported.'
for command in nft systemd-run; do command -v "$command" >/dev/null || fail 'Missing prerequisite.'; done
for path in "$ssh_dropin" "$firewall_dir" "$firewall_unit"; do
  [[ ! -e $path && ! -L $path ]] || fail 'Existing hardening path; refusing to adopt it.'
done
for path in /etc/ssh /etc/ssh/sshd_config.d /etc/systemd/system; do
  [[ -d $path && ! -L $path ]] || fail 'Unexpected parent directory.'
done
[[ $(systemctl show -p LoadState --value moscow1-firewall.service) == not-found ]] || fail 'Existing firewall unit.'
systemctl is-active --quiet ssh.service || fail 'Expected active Ubuntu ssh.service.'
tables=$(nft list tables)
[[ ! $tables =~ table[[:space:]]inet[[:space:]]moscow1_guard([[:space:]]|$) ]] || fail 'Owned table already exists.'
install -d -m 0700 /var/backups/moscow1-hardening
mkdir -m 0700 -- "$backup"
cp -a /etc/ssh "$backup/ssh-before"
nft -s list ruleset >"$backup/ruleset-before.nft"
printf '%s\n' "$SSH_CONNECTION" >"$backup/initial-connection"
install -m 0700 -- "$0" "$backup/rollback.sh"
printf '%s\n' "$address" >"$backup/ready"
systemd-run --quiet --unit="$timer" --on-active=5m --timer-property=AccuracySec=1s \
  /bin/bash "$backup/rollback.sh" rollback "$backup"
systemctl is-active --quiet "$timer.timer" || fail 'Rollback timer not armed.'
on_failure() {
  local code=$1
  trap - ERR INT TERM
  restore || echo 'Hardening rollback incomplete; scheduled rollback remains a safety gate.' >&2
  exit "$code"
}
trap 'on_failure $?' ERR
trap 'on_failure 130' INT
trap 'on_failure 143' TERM
cat >"$ssh_dropin" <<'SSH'
# Managed by moscow1-vless pilot hardening
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AuthenticationMethods publickey
SSH
chmod 0600 "$ssh_dropin"
verify_ssh >"$backup/ssh-check.log" 2>&1
install -d -m 0700 "$firewall_dir"
cat >"$firewall_dir/input.nft" <<'NFT'
table inet moscow1_guard {
  chain input {
    type filter hook input priority 10; policy drop;
    iifname "lo" accept
    ct state established,related accept
    ct state invalid drop
    meta l4proto { icmp, ipv6-icmp } accept
    tcp dport { 22, 80, 443, 24443 } ct state new accept
  }
}
NFT
nft --check --file "$firewall_dir/input.nft" >"$backup/nft-check.log" 2>&1
cat >"$firewall_unit" <<'UNIT'
# Managed by moscow1-vless pilot hardening
[Unit]
Description=Moscow pilot owned input firewall table
After=network-pre.target nftables.service
Before=network.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft --file /etc/moscow1-hardening/input.nft
ExecStop=/usr/sbin/nft delete table inet moscow1_guard
[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "$firewall_unit"
systemd-analyze verify "$firewall_unit" >"$backup/unit-check.log" 2>&1
systemctl daemon-reload
systemctl enable --now moscow1-firewall.service >"$backup/firewall-start.log" 2>&1
systemctl reload ssh.service >"$backup/ssh-reload.log" 2>&1
verify_ssh >"$backup/ssh-readback.log" 2>&1
systemctl is-active --quiet moscow1-firewall.service
[[ $(systemctl is-enabled moscow1-firewall.service) == enabled ]]
systemctl is-active --quiet ssh.service
nft list table inet moscow1_guard >"$backup/firewall-readback.nft"
touch "$backup/applied"
trap - ERR INT TERM
echo 'Applied with five-minute automatic rollback. Keep this session; verify a NEW root key SSH session, then confirm from it.'
