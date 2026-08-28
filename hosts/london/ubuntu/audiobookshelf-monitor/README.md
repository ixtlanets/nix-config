# London Audiobookshelf monitor

Independent runtime checks for the public Audiobookshelf ingress. This bundle
does not deploy or restart Vaultwarden, Caddy, Tailscale, or Audiobookshelf.

Every five minutes the timer verifies:

- the Moscow upstream status endpoint over Tailscale;
- the public HTTPS status endpoint;
- that the public TLS certificate remains valid for at least seven days.

Failures make `audiobookshelf-monitor.service` enter the failed state and are
recorded in the system journal.

Deploy from the repository root:

```sh
hosts/london/ubuntu/audiobookshelf-monitor/deploy.sh
```

Check it manually:

```sh
ssh ubuntu@london \
  'sudo systemctl start audiobookshelf-monitor.service && \
   systemctl status audiobookshelf-monitor.service --no-pager && \
   systemctl list-timers audiobookshelf-monitor.timer --no-pager'
```

Inspect failures:

```sh
ssh ubuntu@london \
  'journalctl -u audiobookshelf-monitor.service --since today --no-pager'
```
