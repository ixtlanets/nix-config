const HOST = "config.nikcode.xyz";
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
