# Home Assistant (container) + mosquitto

## Что работает

- **Home Assistant** (container, не HAOS): http://um790pro:8123 — по LAN и
  tailscale. Add-on'ов нет; вместо них — соседние контейнеры в этом же compose.
- **mosquitto** — MQTT-брокер для связки HA ↔ frigate. На хост слушает только
  `127.0.0.1:1883`; frigate ходит в брокера через общую docker-сеть `hamqtt`.
- **frigate** подключён официальной интеграцией — `config/custom_components/frigate`,
  закоммичен релиз v5.15.6. При обновлении заменить каталог на содержимое
  `custom_components/frigate` из нового релиза
  (github.com/blakeblackshear/frigate-hass-integration/releases) и
  `docker compose restart homeassistant`.

## Первый запуск (выполнен 2026-09-22)

1. `docker compose up -d` в этом каталоге.
2. Онбординг http://um790pro:8123 — создание админа, вручную.
3. MQTT: Настройки → Устройства и службы → Добавить интеграцию → MQTT;
   broker `127.0.0.1`, port `1883`, без авторизации (yaml-настройки брокера
   в современных HA нет — только UI).
4. Интеграция frigate: Добавить → Frigate; url `http://127.0.0.1:8971`
   (интеграция задаётся с точки зрения хоста; сам она ходит на
   `http://frigate:5000` через общую сеть `hamqtt`) и long-lived token из
   frigate (frigate → Settings → API tokens; auth включён).

## Конфигурация

- В git: `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`,
  vendored-интеграция.
- Не в git (см. `config/.gitignore`): `.storage/`, `*.db*`, `secrets.yaml`,
  бэкапы, deps, tts, логи. Секреты — через `!secret` в `secrets.yaml`
  (шаблон: `secrets.yaml.example`).
- `recorder` ограничен: `purge_keep_days: 10` + exclude шумных доменов —
  страховка для корня, забитого на 94%.

## Обновление

```bash
# 1. Бэкап перед обновлением: HA → Настройки → Система → Бэкапы
#    (попадёт в config/backups/, в git не попадает), либо вручную:
#    tar czf ~/backups/home-assistant-config-$(date +%F).tar.gz -C ~/nix-config/hosts/um790pro/docker/home-assistant config
cd ~/nix-config/hosts/um790pro/docker/home-assistant
git pull
docker compose pull && docker compose up -d
```

## Типовые операции

```bash
docker compose ps
docker compose logs -f homeassistant
docker compose logs -f mosquitto
# что публикует frigate в брокер:
docker exec mosquitto mosquitto_sub -t 'frigate/#' -v
```

Перезапуск frigate после правки его конфига:
`cd ~/nix-config/hosts/um790pro/docker/frigate && docker compose restart frigate`.
