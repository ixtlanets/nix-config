# UM790 Pro Proxmox migration: Codex session research

Date: 2026-11-09. Historical reconstruction, not a new infrastructure audit.

## Scope and confidence

Only this report was created. No SSH connection, service/VM operation, configuration change, rebuild, or secret decryption was performed. Existing logs and local migration receipts were read. The lead agent separately owns today's live resource checks.

Discovery used a narrow JSONL glob rooted at the Codex sessions directory, followed by Proxmox/Grishin searches and reads of matched logs. An initial home-root glob encountered unrelated inaccessible directories; subsequent searches were rooted directly at the sessions directory. Broad content searches exceeded retained-output limits and were narrowed by date and exact session. No inaccessible data was bypassed.

JSONL references cite physical lines of original first-party logs. Duplicate event/response records are not separate actions. Historical assistant acceptance summaries are not fresh independent tests. No passwords, tokens, private keys, cookie values, or secret configuration bodies are reproduced.

**Time convention:** JSONL timestamps are UTC; filenames are local session-start times. Dates/times below are Europe/Moscow (UTC+03:00). A November 6 session file therefore contains November 7–8 actions.

## Bottom line

The remembered plan is real: **separate personal and Grishin Robotics Omarchy VMs**, plus infrastructure/storage roles, Frigate LXC, and optional Windows. It was not a plan to put GR into the personal VM. Personal migration expanded into multi-day recovery of projects, instructions, skills, browser state, and Codex history. The reviewed session explicitly deferred GR to a separate work environment and excluded GR projects and three GR conversations from personal imports. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>) [main:14071](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14071>) [main:19236](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19236>) [main:19679](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19679>)

No assigned GR VM ID, completed GR guest, or completed evacuation of M1 Max was established. A bounded “migration completed” milestone did **not** mean completion of the entire original all-host plan.

## Primary sessions

| Session | Role and evidence |
| --- | --- |
| 01a1ae3b-6fb9-7f82-a835-a318e6f24f7f | Main Codex Desktop session starts **Nov 6 03:21**; original request [main:15](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L15>), explicit VM/storage plan [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>), last reviewed milestone **Nov 8 16:34** [main:22751](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22751>). |
| 01a1ae3b-f88a-7a12-87aa-428a26e36ac2 | Child M1 inventory starts **Nov 6 03:22**; metadata identifies the parent and /root/m1max_inventory. Initial and expanded inventories: [M1 inventory:81](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L81>) [M1 inventory:139](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L139>). |

## Original plan versus execution

### Original request and isolation contract

At **Nov 6 03:21**, the user wanted UM790 Pro to become a server: migrate personal OpenClaw from Zenbook, work OpenClaw from M1 Max, remaining Zenbook services, preserve existing UM790 services, and leave only llama-server on M1. Isolation included browser identities, Docker/local Postgres, and interactive agent↔human browser handoff. This first turn authorized discussion/research, not immediate migration. [main:15](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L15>)

At **03:42**, the design was clarified: remove personal/work A2A in the future configuration; treat M1 vault as work rather than reclassifying every personal-looking folder; use persistent Linux graphical sessions, with independent Windows on demand. This was a design decision, not proof old A2A tunnels had been removed. [main:396](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L396>)

At **13:42**, the detailed target was:

| Planned role | Intended workload | Actual later evidence |
| --- | --- | --- |
| Personal Omarchy VM | Personal OpenClaw, Codex, browsers, Docker, local Postgres | **VM103**, later enlarged and filled with projects/history. |
| Work Omarchy VM | GR OpenClaw, work data, separate browsers | Explicitly deferred; creation not shown. |
| Infrastructure Linux VM | HA, MQTT, Audiobook Ops, tar1090/background jobs | Actual split: **VM101** HA/MQTT, **VM102** audio; tar1090 checks later disabled. |
| Storage VM | Google archives, no shared home with work | Completion not established; archive remained on Samsung. |
| Frigate LXC | Cameras/GPU | **CT100**, hardware decode historically accepted. |
| Optional Windows VM | Independent on-demand service | **VM104**, imported and left off. |

Sources: layout [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>); order [main:11819](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L11819>); HA/Frigate [main:12655](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12655>); VM102–104 and GR deferral [main:14071](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14071>).

Constraints included account-free templates, no cross-contour cloning of browser credentials/profiles, concurrent VirGL desktops, consistent DB copies, preservation of dirty Git trees, backing chains/UEFI/NVRAM/TPM, and stopping source agents before starting replacements. These are **acceptance requirements**, not evidence that a second work VM passed them. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>)

### Dated timeline and durations

| Moscow time | Recorded milestone | Meaning |
| --- | --- | --- |
| Nov 6 03:21 | Assessment begins | Original all-host request. [main:15](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L15>) |
| Nov 6 04:03 | Ubuntu 24.04/XFCE pilot: 4 vCPU/8 GiB, Codex/Brave | Existing UM containers reportedly stayed running. [main:979](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L979>) |
| Nov 6 11:10–12:05 | Gliff/Omarchy input/browser pilot | Multiple clipboard/input iterations. [main:2436](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L2436>) [main:2872](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L2872>) [main:3549](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L3549>) |
| Nov 6 13:42 | Kingston/Samsung and personal/GR plan | Proposal before destructive installation. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>) |
| Nov 6 16:09:12 → 19:32:43 | Backup data point → full verified completion | **3 h 23 m 31 s**, backup/verification interval, **not total downtime**. [backup receipt](</home/nik/migration/um790pro-2026-11-06/SUMMARY.txt#L1-L14>) |
| Nov 6 19:34 | Backup ready; Wi-Fi/NAT selected | Installation not yet begun. [main:8680](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L8680>) |
| Nov 7 00:34 | Proxmox unattended Kingston boot succeeds | ~5 h after backup-ready summary; elapsed session span, **not measured outage**. [main:11128](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L11128>) |
| Nov 7 01:14 | Restoration order reiterated | Old UM services first; personal third, **GR fourth**, Windows later. [main:11819](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L11819>) |
| Nov 7 01:43 | HA/MQTT101 and Frigate100 accepted | Devices, MQTT, video/live/review, AMD decode, guest restarts checked. [main:12655](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12655>) |
| Nov 7 03:04 | Audio102, Omarchy103, Windows104 imported | GR explicitly left separate. [main:14071](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14071>) |
| Nov 7 11:33 | Personal OpenClaw survives Zenbook reboot | 176 sessions checked; vault byte comparison; offsite backup incomplete. [main:17933](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L17933>) |
| Nov 7 19:17 | Audit admits incomplete personal migration | Global skills/instructions and much history omitted. [main:18302](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L18302>) |
| Nov 7 20:05 | Additional projects/worktrees verified | 60.8 GB, 104 Git records, dirty changes in 38 worktrees; GR excluded. [main:19236](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19236>) |
| Nov 7 23:25 | Personal Codex history switched | 2,021 chats = 2,003 Zenbook + 18 VM; three GR excluded; 55.1 GB archive awaiting restore check. [main:19679](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19679>) |
| Nov 8 13:59 | Capacity discussion | VM103 **8 vCPU/24 GiB**, ~11 GiB RAM/166 GiB disk free; heavy build peak unmeasured. [main:20227](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L20227>) |
| Nov 8 16:02–16:23 | Meta Arena history/client repair | 1,038 indexed sessions combined; M3 stale project bindings corrected separately. [main:22062](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22062>) [main:22574](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22574>) |
| Nov 8 16:34 | Pablito reachable from Zenbook/M3 | VPN route repair; M3 exception temporary. [main:22751](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22751>) |

Request-to-last-reviewed milestone spans about **61 h 13 m**, including discussion, pauses, user acceptance and follow-up repair. No defensible single total outage duration was found.

## Storage and guest parameters

Original disk plan: **Kingston 1 TB** (former physical Windows) for PVE/VMs, **Samsung 980 PRO 2 TB** (old Linux) retained as migration source, t14s encrypted safety copy. About **814 GiB Google archives were not fully duplicated**. Actual installation: **ext4 root 96 GiB, swap 4 GiB, local-lvm 820.1 GiB**, PVE **9.2.2**, kernel **7.0.2-6-pve**. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>) [install receipt](</home/nik/migration/pve-kingston-install-2026-11-06/README.md#L3-L5>)

The actual method differed from physical Samsung-disconnect proposal: installer VM received **only the Kingston PCI controller via VFIO**, its own OVMF/ISO, no Samsung or host shares. Samsung remained unmounted at installation acceptance. [installation method](</home/nik/migration/pve-kingston-install-2026-11-06/README.md#L3-L5>)

Safety backup occupied **136.51 GiB**; full read-data/restore/verify and independent SHA across **332,622,112,581 bytes**, 768 SQLite checks, isolated PostgreSQL cold restore/dumps and four VM backing chains were verified. Two boot copies displayed frames; guest personal login was **not** claimed at that backup stage. Old Win11 qcow2 had 32 refcount/OFLAG findings and 7 leaks, left unrepaired; Windows-content corruption was not proven. [backup verification](</home/nik/migration/um790pro-2026-11-06/SUMMARY.txt#L1-L19>)

| Guest | Historically established parameters, not current inventory |
| --- | --- |
| VM103 personal | Accepted **Omarchy 4.5.0 pilot**, initially **4 host vCPU/8,192 MiB/48 GiB virtual virtio disk**, q35/OVMF, retained UUID/MAC, **VirGL AMD Radeon 780M**, running/onboot after acceptance. User renamed **nik**, UID/GID 1000; personal Brave/Codex retained, GR absent. Later **8 vCPU/24 GiB**. 48 GiB is **initial** capacity; exact later virtual disk capacity was not established. |
| VM104 Windows | **8 vCPU/12,288 MiB/128 GiB virtual disk**, source TPM preserved, CRB frontend, boot desktop and independent RDP negotiation tested; final stopped/onboot false. Interactive password RDP login not tested in receipt. |
| VM101/CT100 | HA+MQTT / Frigate. Function/autostart historically verified; precise limits not reconstructed. |
| VM102 | Audio stack; exact resource limits not reconstructed. |
| GR guest | Planned, **no approved resource sizing or assigned VMID established**. |

Sources: [main:12819](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12819>) [GUI/Windows acceptance](</home/nik/migration/gui-windows-2026-11-07/RESULT.json#L3-L69>) [main:20227](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L20227>) [main:12655](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12655>) [main:14071](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14071>).

A proposed24→28 GiB increase and separate **4–6 vCPU/12 GiB dev VM** were **recommendations, not actions**. The host then had ~61 GiB usable memory; separate dev guest plus running Windows would bring nominal allocations to ~62 GiB. This was dev-capacity advice, **not GR sizing/creation**. Docker existed but nik lacked socket access; rootless pilot was suggested. [main:20227](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L20227>)

The physical-install receipt records a **newer verified coldpoint at Nov 6 23:48:21 MSK**, after the earlier broad backup. At installation acceptance, the old three VMs and ten containers were offline on Samsung and still required restoration; initial pilot networking was not yet production segmentation/VPN. This clarifies that the early backup receipt is not the final pre-install data point. [Final coldpoint and offline source state](</home/nik/migration/pve-kingston-install-2026-11-06/README.md#L25-L31>)

## Network and likely SSH targets

- **Physical PVE:** Wi-Fi pvewifi0, DHCP **192.168.1.241**, HTTPS **:8006**, root/PAM. No router reservation was created; hardware MAC/client-ID retained the lease. Management stayed direct and separate from guest VPN. Root SSH used dedicated pinned-key local helper, not necessarily old um790pro identity. [management access](</home/nik/migration/pve-kingston-install-2026-11-06/README.md#L7-L21>)
- **Old um790pro alias:** nik@**100.95.213.117**, old CachyOS identity; **do not assume current PVE access**. Historical M1 nik@**192.168.1.174** via UM ProxyJump; M3 LAN **192.168.1.144**, Tailscale**100.109.51.2**. [main:30](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L30>)
- **VM103:** private **10.77.6.103**, vmbr0 gateway/DNS**10.77.6.1**. Approved guests included .2pilot,.102audio,.103Omarchy,.104Windows. Guest IPv6 blocked, DNS intercepted to sing-box, external guest flows fail-closed while management stayed direct. [main:12841](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12841>) [main:12850](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12850>)
- **Actually tested LAN command from M3:** `TERM=xterm-256color ssh -o IdentitiesOnly=yes -i ~/.ssh/id_rsa_1 -p 22103 nik@192.168.1.241`. The explicit non-default key corrects an earlier failed instruction. [main:17989](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L17989>)
- **VM103 Tailscale:** **100.116.87.104**, node personal-openclaw. Pablito route: Moscow Caddy→VM **:18789**. M3 needed an explicit Tailscale route. [main:14511](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14511>) [main:22701](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22701>)
- **Home network:** vmbr1 **10.77.7.10** Frigate/**10.77.7.20** HA; narrow VM103→HA TCP8123 MCP exception. LAN HA **:8123**,Frigate **:8971**; MQTT closed to home LAN. [main:14633](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14633>) [main:12655](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12655>)

These historical leads were sent to the lead during research and still require its live read-only validation. The historical route audit also warned that the repository Caddy configuration still targeted the old Zenbook: blindly redeploying it could revert the accepted public route. No configuration was changed for this research. [Route audit](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22701>)

## Problems and acceptance gaps

1. **GUI/input consumed hours.** SPICE keyboard grab interfered with local Hex; SPICE_NOGRAB did not end investigation. TigerVNC then Gliff were tried. Gliff paste initially yielded only v/no text; a window-specific native Hyprland path restored ASCII/Cyrillic multi-line paste. **Bitwarden password-labelled clipboard exclusion was intentional and left intact.** Agent→human→agent handoff remained an explicit user acceptance checkpoint. [main:1145](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L1145>) [main:1544](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L1544>) [main:2436](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L2436>) [main:2872](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L2872>) [main:3549](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L3549>)
2. **Firmware/Wi-Fi needed real reboot acceptance.** AMI BBS priority reordered boots; EFI BootOrder alone was insufficient. User selected Kingston first and handled Boot Option Restored. AX210 firmware/initramfs/link identity and TCP DNS were required; uncached UDP DNS failed while TCP/trusted DoH worked. [boot/network acceptance](</home/nik/migration/pve-kingston-install-2026-11-06/README.md#L13-L21>)
3. **Image compatibility was not just copying.** PVE QEMU 11.0 did not support original pc-q35-11.1; current q35 selected. Backing chains flattened/imported with comparisons. VirGL shared renderD128 with Frigate without GPU PCI passthrough. Windows TPM required separate handling; ACPI shutdown inconsistent, native Windows shutdown used. [main:12819](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L12819>) [import checks](</home/nik/migration/gui-windows-2026-11-07/RESULT.json#L43-L82>)
4. **Personal migration was initially incomplete.** Audit found 48/51 global skills absent; Codex global instructions/rules/agent profiles/hooks missing; none of 1,955 pre-snapshot conversation IDs in target DB/index. JSONL presence did not imply Desktop-visible/resumable history. Assets and 15.9 GB Codex worktrees were omitted. Repair later verified 60.8 GB and switched merged history. Orca hooks stayed disabled because Orca was absent; old plugin availability was not restored merely by same-name skill recovery. [main:18302](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L18302>) [main:19236](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19236>) [main:19679](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19679>)
5. **Live clients obstructed history cutover.** During later rehearsal a new connection/task appeared, so active DB was preserved pending client quiescence. M3 local project bindings hid target chats; full brief ChatGPT exit and client binding repair restored visibility. [main:21327](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L21327>) [main:22574](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22574>)
6. **Local backup success ≠ offsite protection.** First 31 GB archive passed restore but mtime precision needed manifest correction; Moscow transfer timed out and London lacked space. Nightly timer remained off. After broader inclusions a 55.1 GB archive still awaited restore validation at Nov 7 23:25. Do not infer unattended offsite protection completed. [main:17933](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L17933>) [main:18302](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L18302>) [main:19679](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19679>)
7. **VPN caused separate reachability regressions.** Direct PVE→VLESS failed at one checkpoint; Warsaw traffic temporarily used London tunnel while retaining Warsaw egress. Pablito client failures later traced to public-IP routing through VPN. Zenbook exception persisted; M3 route temporary and reboot-sensitive. [main:17933](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L17933>) [main:22751](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L22751>)
8. **Samsung is not a timeless rollback after new writes.** Once production DB writes move, booting old Samsung alone discards new state without reverse migration. Google/virtiofs data needs separate backup policy; consumer VM backup is not source-data protection. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>)

## Remaining GR/work plan

Strong evidence: explicit independent work VM design, followed by GR deferment and exclusion of its projects/three chats. **No reviewed evidence identifies goar-team as an already-created GR guest.** gr/work/goar-team remain search hints, not interchangeable proof of deployed identity. [main:4869](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L4869>) [main:14071](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L14071>) [main:19236](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19236>) [main:19679](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L19679>)

| M1 work component | Historical inventory and planning consequence |
| --- | --- |
| GR OpenClaw | ~13 GB state, launchd gateway, LinkedIn/funding agents; CDP 18801–18804 configured but not listening at check. Validate actual sandbox/browser function. [M1 inventory:81](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L81>) [M1 inventory:139](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L139>) |
| Work vault | ~46 GB; initially mixed-looking names, subsequently user/parent clarified work ownership. Do not reclassify merely from names. [M1 inventory:139](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L139>) [main:396](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L396>) |
| GR News | PostgreSQL 16.11 data ~4 GB, app DB 3852 MB/test 18 MB, Next.js :3000. Need consistent DB migration, not checkout alone. [M1 inventory:139](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L139>) |
| Other work services | Indexary :4185; vault dashboard/cloudflared :8787/:20241; GRX interviews :3027/:3028 (~1.3 GB); Syncthing; llama dashboard :8081/:8082; Ollama :11434. Exact inclusion requires work-plan decision. [M1 inventory:139](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L139>) |
| Browser bridges | M1 Brave OpenClaw/ChatGPT extensions, macOS-arm64 native messaging and LinkedIn Helper MCP bridge need Linux equivalents/session/key-storage/handoff acceptance. Personal pilot does not prove GR-specific bridge portability. [M1 inventory:81](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L81>) |
| Residual M1 role | Keep llama-server :8080; original goal otherwise evacuate M1, not move model serving to x86. [main:15](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-21-33-01a1ae3b-6fb9-7f82-a835-a318e6f24f7f.jsonl#L15>) [M1 inventory:81](</home/nik/.codex/sessions/2026/11/06/rollout-2026-11-06T03-22-08-01a1ae3b-f88a-7a12-87aa-428a26e36ac2.jsonl#L81>) |

Next planning gates, **not infrastructure actions authorized by this report**:

1. Lead verifies current inventory/CPU/memory/thin pool. Do not reserve GR ID or promise capacity from initial 4 vCPU/8 GiB personal sizing.
2. Choose distinct work VM sizing, credentials/profiles/home, network and backups; preserve isolation and revisit planned A2A removal at work cutover.
3. Inventory M1 changes since Nov 6; old inventory is a starting point, not live truth.
4. Rehearse GR-specific browser bridges and handoff; migrate consistent vault/state/DB plus projects, resumable histories/assets/instructions without repeating personal omissions.
5. Stop old writers before new; verify application function and offsite restore before declaring GR complete or freeing M1 to llama-only.

Conclusion: **personal environment migrated with substantial follow-up repair; GR deferred**, not “both isolated environments fully migrated.”
