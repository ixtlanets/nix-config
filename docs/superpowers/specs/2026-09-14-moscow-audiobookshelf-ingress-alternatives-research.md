# Moscow Audiobookshelf ingress alternatives

**Date:** 2026-09-14  
**Question:** how to bypass the degraded `132.145.52.74:443` path without
requiring immediate access to the Oracle Cloud console.

## Current constraints

The repository's production path is Cloudflare DNS-only -> London Caddy ->
Moscow over Tailscale. Moscow Audiobookshelf itself listens on
`0.0.0.0:13378`; its host is an ARM64 Raspberry Pi on EOL Ubuntu 21.10. The
current design deliberately avoids a home-router port forward and bounds the
EOL risk by keeping Moscow off the public Internet
([Moscow bundle](../../../hosts/moscow/ubuntu/audiobookshelf/README.md),
[London ingress](../../../hosts/london/ubuntu/vaultwarden/README.md)).

Read-only observation on 2026-09-14:

- Moscow LAN address: `192.168.1.61`; router: `192.168.1.1` (Keenetic web
  server); observed public egress IPv4: `46.188.23.6`.
- No Caddy or Certbot is installed on Moscow; TCP `443` is free.
- The earlier deployment handoff records that public TCP `13378` was
  closed/filtered, which is consistent with having no NAT rule; it does not
  prove that the ISP address is CGNAT.
- Frankfurt exposes VLESS+Reality on TCP `443` and its camouflage endpoint on
  TCP `80`. Its Tailscale daemon currently reports `NeedsLogin`; its WireGuard
  overlay has no Moscow peer.

## Options

### 1. Direct home port-forward to a local TLS reverse proxy

**Feasibility:** yes, if Keenetic's WAN address is a public IPv4 and inbound
TCP `443` is allowed by the ISP. Keenetic states that NAT port forwarding needs
a public WAN address and will not work with a private/CGNAT address
([Keenetic port-forward troubleshooting](https://help.keenetic.com/hc/ru/articles/115002886909-%D0%A7%D1%82%D0%BE-%D0%B4%D0%B5%D0%BB%D0%B0%D1%82%D1%8C-%D0%B5%D1%81%D0%BB%D0%B8-%D0%BD%D0%B5-%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B0%D0%B5%D1%82-%D0%BF%D1%80%D0%BE%D0%B1%D1%80%D0%BE%D1%81-%D0%BF%D0%BE%D1%80%D1%82%D0%BE%D0%B2-%D0%B4%D0%BB%D1%8F-%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D0%B9-NDMS-2-11-%D0%B8-%D0%B1%D0%BE%D0%BB%D0%B5%D0%B5-%D1%80%D0%B0%D0%BD%D0%BD%D0%B8%D1%85)).

The safe shape is `books.nikcode.xyz` as a DNS-only A record -> Keenetic
TCP `443` forward -> Caddy -> `127.0.0.1:13378`. Do not forward the raw ABS
port. Caddy can issue and renew a public certificate when DNS points at the
host and TCP `443` reaches it; TLS-ALPN-01 operates on port `443`
([Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https),
[Let's Encrypt challenge types](https://letsencrypt.org/docs/challenge-types/)).
If the public address changes, Cloudflare documents updating the A record by
API as the DDNS pattern
([Cloudflare dynamic DNS](https://developers.cloudflare.com/dns/manage-dns-records/how-to/managing-dynamic-ip-addresses/)).

This preserves the existing Absorb URL and avoids all relay/CDN bandwidth
limits. Its drawbacks are residential uplink/availability, a router change,
DDNS, and materially widening the attack surface of the EOL Moscow host. A
better production variant is to terminate Caddy on a supported, always-on host
behind the same Keenetic and proxy only ABS to `192.168.1.61:13378`. UM790Pro is
not such a host: despite overlapping `192.168.1.0/24` addressing, it is at a
different site and currently reaches Moscow only through Tailscale.

**Required gate:** compare Keenetic WAN IPv4 with `46.188.23.6`, create a
temporary narrowly-scoped TCP forward, and test from an actually external
network before DNS cutover. Router and firewall changes are owner-gated.

### 2. Tailscale Funnel directly on Moscow

**Feasibility:** immediate and does not require an inbound port. Funnel can
publish the local HTTP service through Tailscale's public TLS relay. It requires
MagicDNS, tailnet HTTPS, and a `funnel` node attribute
([Funnel](https://tailscale.com/docs/features/tailscale-funnel)).

It cannot preserve `books.nikcode.xyz`: Funnel only uses the tailnet's
`*.ts.net` names and only ports `443`, `8443`, or `10000`. Traffic also has
non-configurable bandwidth limits
([Funnel limitations](https://tailscale.com/docs/features/tailscale-funnel)).
Tailscale describes Funnel as best for temporarily sharing one resource and
specifically recommends device sharing, not Funnel, for persistent Plex-like
media access
([Funnel vs. sharing](https://tailscale.com/docs/reference/funnel-vs-sharing)).

Therefore Funnel is the best **reversible canary/emergency workaround**: point
one Absorb client at the generated Moscow `.ts.net` URL and verify login,
cover, playback, Range seek, WebSocket reconnect, and progress. It is not the
preferred final production ingress.

For a fixed set of users, a private Tailscale path/device share is stronger
than Funnel: it keeps ABS off the public Internet and matches Tailscale's own
media-server recommendation, at the cost of requiring Tailscale on every
client and a different server URL.

### 3. Cloudflare Tunnel or orange-cloud proxy

**Feasibility:** technically excellent but unsuitable as the default solution
on a self-service plan. `cloudflared` on Moscow needs only outbound TCP/UDP
`7844`, so no router port or public IPv4 is required
([Tunnel firewall requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)).
A published application can keep `books.nikcode.xyz` and proxy
`http://localhost:13378`; without a Cloudflare Access application it remains
public and ABS supplies authentication
([publish an application](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)).

Cloudflare supports WebSockets and cached byte ranges when the origin supplies
`Content-Length`; its proxy has connection timeouts and self-service cacheable
objects are limited to 512 MB
([cache and Range behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/),
[connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)).
More importantly, Cloudflare's current Free/Pro/Business CDN terms allow it to
limit or disable delivery when a disproportionate share is audio or other
large files, unless the appropriate paid service is used
([Application Services terms, CDN](https://www.cloudflare.com/en-gb/service-specific-terms-application-services/)).
Cloudflare explicitly says public-hostname Tunnel traffic is subject to that
large-file restriction
([large-file delivery policy](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/)).

Thus this would probably fix the ISP route and preserve the URL, but it is not
a ToS-safe production path for self-hosted audiobook streaming. Use only after
an appropriate paid/Enterprise agreement or a deliberate acceptance of the
service risk; do not treat a successful canary as production approval.

### 4. Existing Frankfurt VPS

Frankfurt is reachable and avoids the Oracle IP, but it is not a quick safe
drop-in. TCP `443` and `80` are both owned by the production
`reality-ezpz-engine-1` container; Moscow is not on Frankfurt's WireGuard
overlay, and Frankfurt Tailscale requires re-enrollment. A separate HTTPS port
would still need a public listener, certificate automation, a Moscow transport
(Tailscale re-enrollment, new WireGuard peer, or managed reverse SSH tunnel),
and client URL changes.

Sharing TCP `443` is technically possible only by placing an SNI-aware L4
multiplexer in front of both REALITY and a web proxy. That changes the critical
VLESS ingress, may affect every existing proxy client, and adds a coupled
failure domain. It should not be used as an emergency audiobook fix. A second
VPS/IP dedicated to ordinary HTTPS would be simpler and safer than multiplexing
the existing Frankfurt endpoint.

## Recommendation

1. **Now:** enable a narrowly-scoped Tailscale Funnel on Moscow as a canary, or
   use private Tailscale/device sharing if all intended clients can run it.
   This directly answers whether removing London fixes cover and audio transfer
   without touching router, DNS, Oracle, or VLESS.
2. **Preferred production path without London:** port-forward TCP `443` at
   Keenetic to a Caddy instance on a supported, always-on host at the Moscow
   site, proxy only to Moscow ABS, keep Cloudflare DNS-only, and add DDNS plus
   external monitoring. If Moscow itself is the only always-on host, this path
   should wait for its supported-LTS migration unless the EOL exposure is
   explicitly accepted as a temporary risk. Proceed only after confirming the
   WAN address is truly public and an external port canary succeeds.
3. **Do not select Cloudflare Tunnel on a self-service plan** for the permanent
   audiobook data plane because its public hostname traverses the CDN and the
   terms explicitly cover disproportionate audio/large-file traffic.
4. **Do not disturb Frankfurt VLESS `:443`** for this incident. If direct home
   ingress is impossible, provision a dedicated inexpensive VPS/IPv4 ingress
   rather than multiplexing the existing REALITY endpoint.
