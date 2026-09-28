# Frigate

NVR: `ghcr.io/blakeblackshear/frigate:stable`, композ в этом каталоге.
Конфиг и записи на хосте: `/home/nik/services/frigate/{config,storage}`.
Домашняя страница HA-связки (MQTT, интеграция): ../home-assistant/README.md.

## Доступ через Tailscale

`https://um790pro.tailf108.ts.net` — Frigate UI внутри tailnet, с настоящим
сертификатом Let's Encrypt (выдаёт Tailscale Serve), без порта в URL.

Устроено так (настройка живёт в состоянии tailscaled, НЕ в nix):

```bash
# на um790pro, один раз; переживает перезагрузку
tailscale serve --bg --yes https+insecure://192.168.1.241:8971
```

- `https+insecure://` — не «отключённая проверка», а флаг serve «ходить в
  цель с самоподписанным сертом»; снаружи, в браузер, отдаётся LE-серт.
- Цель — LAN IP frigate (порты прибинжены к 192.168.1.241, не к loopback).
- Serve публикует только 443/UI+API. RTSP (8554) и WebRTC (8555) остаются
  LAN-only; live-видео в браузере через tailnet играет по MSE через 8971.
- Auth frigate остаётся вторым слоем: без логина API отвечает 401.
- Наружу (funnel) ничего не публикуется — только tailnet.
- Выключить: `tailscale serve --https=443 off` (или `tailscale serve reset`).

Проверка (с любой машины tailnet):

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://um790pro.tailf108.ts.net/          # 200
curl -s -o /dev/null -w '%{http_code}\n' https://um790pro.tailf108.ts.net/api/config # 401
```

Историческая заметка: до 2026-09-29 на ноде висело serve-правило
`um790pro-1...` → 127.0.0.1:18789 (остаток экспериментов с openclaw gateway,
юнит disabled, порт никем не слушался) — убрано `tailscale serve reset`.

## Типовые операции

```bash
cd ~/nix-config/hosts/um790pro/docker/frigate
docker compose restart frigate   # после правки config.yml
docker compose logs -f frigate
```
