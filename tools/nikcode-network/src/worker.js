import ruGeoIP from "./geoip-ru.js";

export const HOST = "config.nikcode.xyz";
export const OWN_SUBSCRIPTION_HOST = "subscriptions.nikcode.xyz";
export const PILOT_RULES_SHA256 = "bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d";
export const PILOT_RULES_BYTES = 50096;
export const PILOT_RULES_PATH = "/rules/geoip-ru-" + PILOT_RULES_SHA256 + ".srs";
export const OWN_RULES_URL = "https://" + OWN_SUBSCRIPTION_HOST + PILOT_RULES_PATH;
const FORMATS = new Set(["sing-box", "sing-box-macos", "sing-box-linux", "sing-box-android", "sing-box-ios", "sing-box-ios-legacy", "outbounds", "throne", "hiddify", "incy", "happ"]);
const BASE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  "CDN-Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
  "Strict-Transport-Security": "max-age=31536000",
};

export async function tokenHash(token) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function nodes(config) {
  const { host, port, naive, vless } = config.entry;
  return [
    {
      type: "naive", tag: "primary-naive", server: host, server_port: port,
      username: naive.username, password: naive.password,
      domain_resolver: "bootstrap",
      tls: { enabled: true, server_name: host },
    },
    {
      type: "vless", tag: "primary-vless", server: host, server_port: port,
      uuid: vless.uuid, flow: "xtls-rprx-vision", domain_resolver: "bootstrap",
      tls: {
        enabled: true, server_name: vless.server_name,
        utls: { enabled: true, fingerprint: vless.fingerprint || "chrome" },
        reality: { enabled: true, public_key: vless.public_key, short_id: vless.short_id },
      },
    },
  ];
}

function publicIPv4DNSRules(legacy = false) {
  // Empty NOERROR lets dual-stack applications use A without a DNS error/retry.
  // 1.11 cannot use the predefined action introduced in 1.12.
  return [{ query_type: ["AAAA"], ...(legacy
    ? { action: "route", server: "empty-aaaa", disable_cache: true }
    : { action: "predefined", rcode: "NOERROR" }) }];
}

function publicIPv4RouteRules() {
  // Tailscale ULA, loopback and link-local IPv6 remain usable. Public literal
  // IPv6 must fail quickly before any domain, GeoIP or UDP routing exception.
  return [
    { ip_is_private: true, action: "route", outbound: "direct" },
    { ip_cidr: ["ff00::/8"], action: "route", outbound: "direct" },
    { ip_version: 6, action: "reject", method: "default", no_drop: true },
  ];
}

// A distinct token namespace prevents a malformed/revoked pilot from ever
// resolving through the shared legacy catalog, even if hashes collide.
export const PILOT_PATH = /^\/s\/(p_[A-Za-z0-9_-]{43})(?:\/sing-box-ios)?$/;
const PILOT_RU_RULE_URL = "https://raw.githubusercontent.com/SagerNet/sing-geoip/eb32cd6ed4a16fcb3bf9a36ccebf28e45716ae84/geoip-ru.srs";
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const NODE_ID = /^[a-z][a-z0-9-]{0,31}$/;

export function validPilot(config) {
  if (config?.schema !== 1 || !Array.isArray(config.nodes) || config.nodes.length < 2
    || !Array.isArray(config.devices) || !config.devices.length) return false;
  if (!config.nodes.every((node) => node && typeof node === "object")
    || !config.devices.every((device) => device && typeof device === "object")) return false;
  const ids = config.nodes.map((node) => node.id);
  if (new Set(ids).size !== ids.length || new Set(config.nodes.map((n) => n.host)).size !== ids.length) return false;
  if (!config.nodes.every((node) => NODE_ID.test(node.id) && typeof node.enabled === "boolean"
    && typeof node.host === "string" && /^[a-zA-Z0-9.-]+$/.test(node.host)
    && Number.isInteger(node.port) && node.port > 0 && node.port <= 65535
    && node.protocol === "vless" && typeof node.server_name === "string" && node.server_name.length > 0
    && typeof node.public_key === "string" && /^[A-Za-z0-9_-]{43}$/.test(node.public_key)
    && typeof node.short_id === "string" && /^(?:[a-f0-9]{2}){0,8}$/i.test(node.short_id))) return false;
  if (config.ru_domains !== undefined && (!Array.isArray(config.ru_domains)
    || !config.ru_domains.every((d) => typeof d === "string" && /^[a-zA-Z0-9.-]+$/.test(d)))) return false;
  if (config.ru_rules !== undefined && (!Array.isArray(config.ru_rules) || !config.ru_rules.length
    || !config.ru_rules.every((r) => r && Array.isArray(r.ip_cidr) && r.ip_cidr.length
      && Object.keys(r).length === 1 && r.ip_cidr.every((cidr) => typeof cidr === "string")))) return false;
  if (config.magic_dns_suffix !== undefined && (typeof config.magic_dns_suffix !== "string"
    || !/^[a-zA-Z0-9.-]+\.ts\.net$/.test(config.magic_dns_suffix))) return false;
  if (config.subscription_hosts !== undefined && (!Array.isArray(config.subscription_hosts)
    || !config.subscription_hosts.length || new Set(config.subscription_hosts).size !== config.subscription_hosts.length
    || !config.subscription_hosts.every((host) => [HOST, OWN_SUBSCRIPTION_HOST].includes(host)))) return false;
  if (config.rules_url !== undefined && config.rules_url !== OWN_RULES_URL) return false;
  const hashes = config.devices.map((device) => device.hash);
  const deviceIds = config.devices.map((device) => device.id);
  const uuids = [];
  if (new Set(hashes).size !== hashes.length || new Set(deviceIds).size !== deviceIds.length) return false;
  for (const device of config.devices) {
    if (!NODE_ID.test(device.id) || !/^[a-f0-9]{64}$/.test(device.hash) || typeof device.enabled !== "boolean"
      || typeof device.tailscale !== "boolean" || (device.tailscale && !config.magic_dns_suffix)
      || (device.rule_set_mode !== undefined && !["inline", "remote"].includes(device.rule_set_mode))
      || !device.credentials || Object.keys(device.credentials).length !== ids.length) return false;
    for (const id of ids) {
      const credential = device.credentials[id];
      if (!credential || !UUID.test(credential.uuid)) return false;
      uuids.push(credential.uuid.toLowerCase());
    }
  }
  return new Set(uuids).size === uuids.length;
}

export function singBoxPilot(config, device) {
  const active = config.nodes.filter((node) => node.enabled);
  if (!active.length) throw new Error("No active pilot nodes");
  const ruDomains = [...new Set(["ru", "su", "xn--p1ai", ...(config.ru_domains || [])])];
  const tailnet = device.tailscale;
  const subscriptionHosts = [...new Set([HOST, ...(config.subscription_hosts || [])])];
  return {
    log: { level: "warn", timestamp: true },
    dns: {
      strategy: "ipv4_only", final: "remote",
      servers: [
        { type: "https", tag: "bootstrap", server: "1.1.1.1", server_port: 443, path: "/dns-query", detour: "direct" },
        { type: "https", tag: "remote", server: "8.8.8.8", server_port: 443, path: "/dns-query", detour: "proxy" },
        { type: "local", tag: "local" },
        ...(tailnet ? [{ type: "tailscale", tag: "ts-dns", endpoint: "ts-ep", accept_default_resolvers: false }] : []),
      ],
      rules: [
        ...(tailnet ? [
          { preferred_by: "ts-dns", action: "route", server: "ts-dns" },
          { domain_suffix: [config.magic_dns_suffix], action: "route", server: "ts-dns" },
        ] : []),
        { domain_suffix: ["local", "lan", "home.arpa"], action: "route", server: "local" },
        ...publicIPv4DNSRules(),
        { domain: [...subscriptionHosts, ...active.map((node) => node.host)], action: "route", server: "bootstrap" },
        { domain_suffix: ruDomains, action: "route", server: "bootstrap" },
      ],
    },
    inbounds: [{
      type: "tun", tag: "tun-in", address: ["198.19.0.1/30", "fdfe:dcba:9876::1/126"],
      mtu: 1400, auto_route: true, strict_route: true, stack: "gvisor",
    }],
    ...(tailnet ? { endpoints: [{ type: "tailscale", tag: "ts-ep",
      state_directory: "tailscale-" + device.id, hostname: device.id,
      ephemeral: false, accept_routes: false, system_interface: false,
      domain_resolver: "bootstrap" }] } : {}),
    outbounds: [
      { type: "urltest", tag: "proxy", outbounds: active.map((node) => node.id),
        url: "https://www.gstatic.com/generate_204", interval: "1m", tolerance: 100,
        interrupt_exist_connections: false },
      ...active.map((node) => ({
        type: node.protocol, tag: node.id, server: node.host, server_port: node.port,
        uuid: device.credentials[node.id].uuid, flow: "xtls-rprx-vision", domain_resolver: "bootstrap",
        tls: { enabled: true, server_name: node.server_name,
          utls: { enabled: true, fingerprint: "firefox" },
          reality: { enabled: true, public_key: node.public_key, short_id: node.short_id } },
      })),
      { type: "direct", tag: "direct", domain_resolver: "bootstrap" },
    ],
    route: {
      auto_detect_interface: true, final: "proxy", default_domain_resolver: "remote",
      rule_set: device.rule_set_mode === "remote" ? [{
        tag: "geoip-ru", type: "remote", format: "binary", url: config.rules_url || PILOT_RU_RULE_URL,
        http_client: { engine: "go", detour: config.rules_url === OWN_RULES_URL ? "direct" : "proxy" }, update_interval: "168h",
      }] : [{ tag: "geoip-ru", type: "inline", rules: config.ru_rules || ruGeoIP }],
      rules: [
        { action: "sniff", inbound: ["tun-in"] },
        { action: "hijack-dns", protocol: "dns" },
        ...(tailnet ? [
          { preferred_by: "ts-ep", action: "route", outbound: "ts-ep" },
          { ip_cidr: ["100.64.0.0/10", "fd7a:115c:a1e0::/48"], action: "route", outbound: "ts-ep" },
          { domain_suffix: [config.magic_dns_suffix], action: "route", outbound: "ts-ep" },
        ] : []),
        ...publicIPv4RouteRules(),
        { ip_cidr: ["100.64.0.0/10"], action: "route", outbound: "direct" },
        { domain: subscriptionHosts, network: "tcp", port: [443], action: "route", outbound: "direct" },
        { domain_suffix: ["local", "lan", "home.arpa"], action: "route", outbound: "direct" },
        { domain_suffix: ruDomains, action: "route", outbound: "direct" },
        { rule_set: ["geoip-ru"], action: "route", outbound: "direct" },
      ],
    },
    experimental: { cache_file: { enabled: true, cache_id: device.id } },
  };
}

export function singBox(config, withInbound = true) {
  return {
    log: { level: "warn", timestamp: true },
    dns: {
      strategy: "ipv4_only",
      servers: [{ type: "https", tag: "bootstrap", server: "1.1.1.1", server_port: 443, path: "/dns-query" }],
      rules: publicIPv4DNSRules(),
    },
    ...(withInbound ? { inbounds: [{ type: "mixed", tag: "local", listen: "127.0.0.1", listen_port: 2080 }] } : {}),
    outbounds: [
      { type: "selector", tag: "proxy", outbounds: ["primary-naive", "primary-vless"], default: "primary-naive" },
      ...nodes(config),
      { type: "direct", tag: "direct" },
    ],
    route: { final: "proxy", default_domain_resolver: "bootstrap", rules: publicIPv4RouteRules() },
  };
}

export function singBoxMac(config) {
  const profile = singBox(config);
  profile.dns = {
    // Keep both address families for the tailnet exception. The following AAAA
    // rule, rather than a global IPv4-only strategy, limits public DNS answers.
    strategy: "prefer_ipv4", final: "remote",
    servers: [
      ...profile.dns.servers.map(({ detour, ...server }) => server),
      { type: "https", tag: "remote", server: "8.8.8.8", server_port: 443, path: "/dns-query", detour: "proxy" },
      { type: "udp", tag: "tailscale", server: "100.100.100.100" },
    ],
    rules: [
      { domain_suffix: ["ts.net"], action: "route", server: "tailscale" },
      ...publicIPv4DNSRules(),
    ],
  };
  profile.inbounds[0].tag = "mixed-in";
  profile.inbounds.push({
    type: "tun", tag: "tun-in", address: ["198.19.0.1/30", "fdfe:dcba:9876::1/126"],
    mtu: 1500, auto_route: true, strict_route: true,
    route_exclude_address: ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "224.0.0.0/4", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8"],
  });
  profile.route.auto_detect_interface = true;
  profile.route.rule_set = [{
    tag: "geoip-ru", type: "remote", format: "binary",
    url: "https://cdn.jsdelivr.net/gh/SagerNet/sing-geoip@rule-set/geoip-ru.srs", http_client: { detour: "proxy" },
  }];
  profile.route.rules = [
    { action: "sniff", inbound: ["mixed-in", "tun-in"] },
    { action: "hijack-dns", protocol: "dns" },
    ...publicIPv4RouteRules(),
    { domain_suffix: ["google.com"], action: "route", outbound: "proxy" },
    { rule_set: ["geoip-ru"], action: "route", outbound: "direct" },
    { network: "udp", action: "route", outbound: "primary-vless" },
  ];
  return profile;
}

export function singBoxIOSLegacy(config) {
  const vless = nodes(config).find((node) => node.type === "vless");
  delete vless.domain_resolver;
  Object.assign(vless, { tag: "proxy", domain_strategy: "ipv4_only", packet_encoding: "xudp" });
  return {
    log: { level: "warn", timestamp: true },
    dns: {
      strategy: "ipv4_only", final: "remote",
      servers: [
        { tag: "bootstrap", address: "https://1.1.1.1/dns-query", detour: "direct" },
        { tag: "remote", address: "https://8.8.8.8/dns-query", detour: "proxy" },
        { tag: "empty-aaaa", address: "rcode://success" },
      ],
      rules: [...publicIPv4DNSRules(true), { outbound: "any", server: "bootstrap" }],
    },
    inbounds: [{
      type: "tun", tag: "tun-in", address: ["198.19.0.1/30", "fdfe:dcba:9876::1/126"],
      mtu: 1500, auto_route: true, strict_route: true, stack: "system",
      route_exclude_address: ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "224.0.0.0/4", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8"],
    }],
    outbounds: [vless, { type: "direct", tag: "direct" }],
    route: {
      auto_detect_interface: true, final: "proxy",
      rule_set: [{
        tag: "geoip-ru", type: "remote", format: "binary",
        url: "https://cdn.jsdelivr.net/gh/SagerNet/sing-geoip@rule-set/geoip-ru.srs", download_detour: "proxy",
      }],
      rules: [
        { action: "sniff", inbound: ["tun-in"] },
        { action: "hijack-dns", protocol: "dns" },
        ...publicIPv4RouteRules(),
        { action: "route", domain_suffix: ["google.com"], outbound: "proxy" },
        { action: "route", rule_set: ["geoip-ru"], outbound: "direct" },
      ],
    },
    experimental: { cache_file: { enabled: true } },
  };
}

export function singBoxLinux(config) {
  const profile = singBoxMac(config);
  Object.assign(profile.inbounds.find((i) => i.type === "tun"), {
    interface_name: "nekoray-tun", auto_redirect: true, stack: "system",
  });
  profile.dns.servers.find((s) => s.tag === "tailscale").bind_interface = "tailscale0";
  profile.route.find_process = true;
  profile.route.rules.splice(2, 0, { process_name: ["tailscaled"], action: "route", outbound: "direct" });
  // Naive carries TCP; Google QUIC and other UDP must reach the VLESS rule.
  profile.route.rules.find((r) => r.domain_suffix?.includes("google.com")).network = "tcp";
  profile.experimental = { cache_file: { enabled: true } };
  return profile;
}

export function singBoxMobile(config) {
  const profile = singBoxMac(config);
  profile.dns.servers = profile.dns.servers.filter((server) => server.tag !== "tailscale");
  profile.dns.rules = profile.dns.rules.filter((rule) => rule.server !== "tailscale");
  profile.route.rule_set[0].http_client = { engine: "go", domain_resolver: "bootstrap" };
  delete profile.inbounds.find((inbound) => inbound.type === "tun").route_exclude_address;
  // Naive carries TCP; UDP uses the separately configured VLESS channel.
  profile.route.rules.find((rule) => rule.domain_suffix?.includes("google.com")).network = "tcp";
  profile.experimental = { cache_file: { enabled: true } };
  return profile;
}

export function vlessLink(config, fingerprint = config.entry.vless.fingerprint || "chrome") {
  const { host, port, vless } = config.entry;
  const query = new URLSearchParams({
    encryption: "none", security: "reality", sni: vless.server_name,
    fp: fingerprint, pbk: vless.public_key, sid: vless.short_id,
    type: "tcp", flow: "xtls-rprx-vision",
  });
  return `vless://${vless.uuid}@${host}:${port}?${query}#Primary%20VLESS`;
}

function naiveLink(config) {
  const { host, port, naive } = config.entry;
  return `naive+https://${encodeURIComponent(naive.username)}:${encodeURIComponent(naive.password)}@${host}:${port}#Primary%20Naive`;
}

export function render(config, format) {
  if (format === "happ") return { type: "text/plain; charset=utf-8", body: vlessLink(config, "firefox") + "\n" };
  if (format === "sing-box-android" || format === "sing-box-ios") return { type: "application/json; charset=utf-8", body: JSON.stringify(singBoxMobile(config), null, 2) + "\n" };
  if (format === "sing-box-linux") return { type: "application/json; charset=utf-8", body: JSON.stringify(singBoxLinux(config), null, 2) + "\n" };
  if (format === "sing-box-ios-legacy") return { type: "application/json; charset=utf-8", body: JSON.stringify(singBoxIOSLegacy(config), null, 2) + "\n" };
  if (format === "sing-box-macos") return { type: "application/json; charset=utf-8", body: JSON.stringify(singBoxMac(config), null, 2) + "\n" };
  if (format === "incy") return { type: "text/plain; charset=utf-8", body: vlessLink(config) + "\n" };
  if (format === "throne") return { type: "text/plain; charset=utf-8", body: naiveLink(config) + "\n" + vlessLink(config) + "\n" };
  if (format === "outbounds") return { type: "application/json; charset=utf-8", body: JSON.stringify(nodes(config), null, 2) + "\n" };
  if (format === "sing-box" || format === "hiddify") {
    return { type: "application/json; charset=utf-8", body: JSON.stringify(singBox(config, format === "sing-box"), null, 2) + "\n" };
  }
  throw new Error("Unknown format");
}

function response(body, status, type, method, extra = {}) {
  return new Response(method === "HEAD" ? null : body, { status, headers: { ...BASE_HEADERS, "Content-Type": type, ...extra } });
}

function validConfig(c) {
  return c?.schema === 1 && c.entry?.host === "notes.nikcode.xyz" && c.entry.port === 443
    && typeof c.entry.naive?.password === "string" && typeof c.entry.naive?.username === "string"
    && typeof c.entry.vless?.uuid === "string" && typeof c.entry.vless?.public_key === "string"
    && typeof c.entry.vless?.short_id === "string" && typeof c.entry.vless?.server_name === "string"
    && Array.isArray(c.subscriptions) && c.subscriptions.every((s) => /^[a-f0-9]{64}$/.test(s.hash)
      && FORMATS.has(s.format) && Array.isArray(s.formats) && s.formats.includes(s.format)
      && s.formats.every((f) => FORMATS.has(f)) && typeof s.enabled === "boolean"
      && (s.vless_fingerprint === undefined || ["chrome", "firefox"].includes(s.vless_fingerprint)));
}

const HOME = `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Короткие технические заметки о работе с текстом, данными и инструментами."><title>Nik Code — технические заметки</title><style>:root{font:17px/1.7 system-ui,sans-serif;color-scheme:light dark}body{max-width:740px;margin:6vh auto;padding:24px}header{padding-bottom:24px}h1{font-size:clamp(2rem,6vw,3rem);line-height:1.15;letter-spacing:-.035em}h2{font-size:1.35rem;line-height:1.35}small,footer{opacity:.65}article{border-top:1px solid #8886;padding:24px 0}footer{padding:24px 0;font-size:.9rem}</style><header><small>NIK CODE / ЗАМЕТКИ</small><h1>Порядок в простых вещах</h1><p>Короткие записи о тексте, данных и повседневных инструментах.</p></header><main><article><small>01 · ТЕКСТ</small><h2>Записывать решения, пока они свежие</h2><p>Полезная заметка отвечает на три вопроса: что изменилось, почему это понадобилось и как проверить результат. Несколько точных предложений часто помогают больше, чем длинное описание без примеров.</p></article><article><small>02 · ДАННЫЕ</small><h2>Проверять восстановление</h2><p>Архив стоит время от времени открывать. Восстановите несколько файлов в отдельную папку и сравните содержимое с оригиналом. Так становится понятно, что сохранённую копию действительно можно использовать.</p></article><article><small>03 · ПРАКТИКА</small><h2>Делать изменения небольшими</h2><p>Когда у каждого шага есть понятная цель, легче оценить результат и вернуться к предыдущему состоянию. Сначала сохраните исходный вариант, затем внесите одно изменение и проверьте его отдельно.</p></article></main><footer>nikcode.xyz · Технические заметки · 2026</footer></html>`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const method = request.method;
    const reply = (body, status = 200, type = "text/plain; charset=utf-8", headers = {}) => response(body, status, type, method, headers);
    if (url.hostname !== HOST || url.protocol !== "https:") return reply("Not found\n", 404);
    if (method !== "GET" && method !== "HEAD") return reply("Method not allowed\n", 405, undefined, { Allow: "GET, HEAD" });
    if (url.pathname === "/") return reply(HOME, 200, "text/html; charset=utf-8", { "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'" });
    if (/^\/s\/p_[A-Za-z0-9_-]{43}(?:\/|$)/.test(url.pathname)) {
      const match = url.pathname.match(PILOT_PATH);
      if (!match || url.search) return reply("Not found\n", 404);
      if (env.PILOT_ORIGIN !== undefined) {
        if (env.PILOT_ORIGIN !== "https://" + OWN_SUBSCRIPTION_HOST) return reply("Service unavailable\n", 503);
        return reply("", 307, undefined, { Location: env.PILOT_ORIGIN + url.pathname });
      }
      let pilot;
      try {
        pilot = JSON.parse(env.PILOT_CONFIG);
        if (!validPilot(pilot)) throw new Error("Invalid pilot");
      } catch { return reply("Service unavailable\n", 503); }
      const hash = await tokenHash(match[1]);
      const device = pilot.devices.find((d) => d.enabled && d.hash === hash);
      if (!device) return reply("Not found\n", 404);
      try {
        return reply(JSON.stringify(singBoxPilot(pilot, device), null, 2) + "\n", 200, "application/json; charset=utf-8", {
          "Profile-Title": "Nik Code Pilot", "Profile-Update-Interval": "1",
        });
      } catch { return reply("Service unavailable\n", 503); }
    }
    let config;
    try {
      config = JSON.parse(env.SERVICE_CONFIG);
      if (!validConfig(config)) throw new Error("Invalid configuration");
    } catch {
      return reply("Service unavailable\n", 503);
    }
    if (url.pathname === "/healthz") return reply('{"status":"ok","service":"subscriptions"}\n', 200, "application/json; charset=utf-8");
    if (url.pathname.startsWith("/qr/")) {
      let share;
      try { share = JSON.parse(env.QR_SHARE || "null"); } catch { /* Missing shares stay private. */ }
      if (!share || url.search || share.path !== url.pathname || !/^\/qr\/[A-Za-z0-9_-]{11,32}\.png$/.test(share.path)
        || !Number.isFinite(share.expires) || Date.now() >= share.expires
        || !config.subscriptions.some((s) => s.enabled && s.hash === share.subscription_hash)
        || typeof share.png !== "string") return reply("Not found\n", 404);
      try {
        const bytes = Uint8Array.from(atob(share.png), (char) => char.charCodeAt(0));
        return reply(bytes, 200, "image/png", { "Content-Disposition": 'inline; filename="max-android-qr.png"', "Referrer-Policy": "no-referrer" });
      } catch { return reply("Not found\n", 404); }
    }
    const match = url.pathname.match(/^\/s\/([A-Za-z0-9_-]{43})(?:\/(sing-box|sing-box-macos|sing-box-linux|sing-box-android|sing-box-ios|sing-box-ios-legacy|outbounds|throne|hiddify|incy|happ))?$/);
    if (!match || url.search) return reply("Not found\n", 404);
    const hash = await tokenHash(match[1]);
    const subscription = config.subscriptions.find((s) => s.hash === hash && s.enabled === true);
    if (!subscription) return reply("Not found\n", 404);
    const format = match[2] || subscription.format;
    if (!subscription.formats.includes(format)) return reply("Not found\n", 404);
    const clientConfig = subscription.vless_fingerprint
      ? { ...config, entry: { ...config.entry, vless: { ...config.entry.vless, fingerprint: subscription.vless_fingerprint } } }
      : config;
    const rendered = render(clientConfig, format);
    return reply(rendered.body, 200, rendered.type, {
      "Profile-Title": "Nik Code",
      "Profile-Update-Interval": "1",
      "Profile-Web-Page-Url": "https://config.nikcode.xyz/",
    });
  },
};
