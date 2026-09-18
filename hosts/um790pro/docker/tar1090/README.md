# RTL-SDR ADS-B на um790pro

Dongle: RTL-SDR V3 Pro (RTL2832U + R820T2, 0bda:2838). Антенна штатная, приём
слабый — позиции самолётов появляются редко, но фиксация бортов (hex, callsign,
высота, скорость) работает.

## Что работает

- **tar1090** — readsb (декодер) + веб-интерфейс: http://192.168.1.241:8080
  Сам читает донгл (USB проброшен в контейнер: `device_cgroup_rules` +
  `/dev/bus/usb`).
- **tar1090-sightings** — логгер пролётов: опрашивает aircraft.json раз в 10 с,
  пишет JSONL в `/home/nik/services/tar1090/sightings/`:
  - `sightings-YYYY-MM-DD.jsonl` — события `first` (борт появился после >2 мин
    тишины) и `seen` (пульс раз в 10 мин, пока виден);
  - поля: ts, event, hex, flight, squawk, category, alt_baro, gs, track,
    lat/lon (когда появятся), messages, rssi, first_seen;
  - `state.json` — состояние first-seen, переживает рестарт.

## Системные требования (сделано один раз, sudo)

- `rtl-sdr` (udev-правила) + `usermod -aG rtlsdr nik`
- blacklist DVB-драйвера: `/etc/modprobe.d/blacklist-rtl2832-dvb.conf`
  (`blacklist dvb_usb_rtl28xxu`) — иначе ядро отбирает донгл у SDR.

## Эксплуатация

```bash
cd ~/nix-config/hosts/um790pro/docker/tar1090
docker compose ps                  # статус
docker compose restart tar1090     # перезапуск декодера
docker compose logs -f tar1090     # логи
docker compose pull && docker compose up -d   # обновление
```

Бортов нет → `docker compose restart tar1090` (донгл иногда зависает по USB).

Пример выборки за день:
`jq -c 'select(.event=="first")' ~/services/tar1090/sightings/sightings-*.jsonl`

Хранить историю heatmap/tреков tar1090 штатно (globe_history) — добавить volume
`/var/globe_history`; пока не нужно, своего логгера достаточно.
