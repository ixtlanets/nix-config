#!/usr/bin/env bash
set -euo pipefail

check_only=false
case "${1:-}" in
  "") ;;
  --check) check_only=true ;;
  *) printf 'Usage: %s [--check]\n' "${0##*/}" >&2; exit 2 ;;
esac

log() {
  printf '[omarchy:syncthing] %s\n' "$*"
}

fail() {
  printf '[omarchy:syncthing] FAIL: %s\n' "$*" >&2
  exit 1
}

self_id="ACDNQPU-AYZTZJD-43ZO52W-DJQNMLQ-PZWOHHQ-M7LCWID-7WUGJ2U-DJJ4RQS"
computer_ids=(
  "$self_id"
  "OKR2QCL-FLJ7JE5-HPWXEKY-SV2BHIA-I24BTUD-CJRVW4Y-VUFRT7H-YFPWOQL"
  "NZ4IHCR-OW6F44P-FPNHA6M-PE44VY7-ZXPCEEB-QSLKP6J-I56KPSA-4AX5VQX"
  "A7OSVWX-MC5LYPV-T4ULXK3-SXLBKLS-BTRFOHM-2YML3BN-SVQ3HOS-LG3VFAV"
  "NQ2KNGN-4ZT42Z3-RGRWOO6-53NLUNM-AQFI25Z-3CED6MP-K2UVMB4-6RW74QV"
  "H5LDAHA-HZQTPI6-S75ZBJ3-LZUFTBM-FW55GVP-DUKYHBB-G73AHIJ-CCCNNQ7"
  "6BIM5VG-DXQR6OY-YYVFQWQ-JJ2UADE-ZY2UDWF-EEX2D6F-UFUCEXT-CN7RQQS"
  "6EKVJ34-S5EJMZF-ZDS3N6X-4OKRXSK-UB4EGIW-IOQHLXH-Z55D4NT-YRS4JAL"
)
mobile_ids=(
  "66MSI5D-LTA44T5-VYMLLN7-2XVEN2F-WBR2CKJ-WWDAEOE-R3VUFIH-4NAZQA6"
  "7LI7XA5-TKD43OY-RZZIYRC-5CE35VG-YTGAYD7-JZEFRZK-XIQKZGP-L4TZXQQ"
)
device_specs=(
  "um790pro|${computer_ids[1]}"
  "x13|${computer_ids[2]}"
  "m1max|${computer_ids[3]}"
  "m3max|${computer_ids[4]}"
  "zenbook|${computer_ids[5]}"
  "desktop|${computer_ids[6]}"
  "um790pro-wsl|${computer_ids[7]}"
  "android-phone|${mobile_ids[0]}"
  "android-tablet|${mobile_ids[1]}"
)
folder_specs=(
  "3y3qt-shfv6|3y3qt-shfv6|$HOME/obsidian-vault|sendreceive|mobile"
  "lavhv-cjakz|Проекты|$HOME/Documents/Проекты|sendreceive|computer"
  "wallpapers|wallpapers|$HOME/wallpapers|sendreceive|computer"
  "разведмобиль|разведмобиль|$HOME/Documents/разведмобиль|sendreceive|computer"
)

systemctl --user start syncthing.service
for _ in {1..30}; do
  syncthing_id="$(syncthing cli show system 2>/dev/null | jq -r '.myID // .myId // ""')" || true
  [[ -n "${syncthing_id:-}" ]] && break
  sleep 1
done
[[ "${syncthing_id:-}" == "$self_id" ]] || fail "unexpected local device ID"

declare -A configured_devices=()
while IFS= read -r device_id; do
  [[ -n "$device_id" ]] && configured_devices["$device_id"]=1
done < <(syncthing cli config devices list)

for spec in "${device_specs[@]}"; do
  IFS='|' read -r name device_id <<< "$spec"
  if [[ -z "${configured_devices[$device_id]:-}" ]]; then
    $check_only && fail "device $name is missing"
    device_json="$(jq -nc --arg id "$device_id" --arg name "$name" '{deviceID:$id,name:$name}')"
    syncthing cli config devices add-json "$device_json"
    log "added device $name"
  fi
done

declare -A configured_folders=()
while IFS= read -r folder_id; do
  [[ -n "$folder_id" ]] && configured_folders["$folder_id"]=1
done < <(syncthing cli config folders list)

for spec in "${folder_specs[@]}"; do
  IFS='|' read -r folder_id label path folder_type sharing <<< "$spec"
  if [[ -z "${configured_folders[$folder_id]:-}" ]]; then
    $check_only && fail "folder $folder_id is missing"
    mkdir -p "$path"
    folder_devices=("${computer_ids[@]}")
    [[ "$sharing" == mobile ]] && folder_devices+=("${mobile_ids[@]}")
    devices_json="$(printf '%s\n' "${folder_devices[@]}" | jq -R . | jq -s .)"
    folder_json="$(jq -nc \
      --arg id "$folder_id" \
      --arg label "$label" \
      --arg path "$path" \
      --arg type "$folder_type" \
      --argjson devices "$devices_json" \
      '{id:$id,label:$label,path:$path,type:$type,devices:($devices | map({deviceID:.}))}')"
    syncthing cli config folders add-json "$folder_json"
    log "added folder $folder_id"
  fi
done

if $check_only; then
  log "topology verified"
else
  log "topology configured"
fi
