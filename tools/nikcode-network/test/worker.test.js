import test from "node:test";
import assert from "node:assert/strict";
import worker, { tokenHash, singBoxLinux, render, singBoxPilot, validPilot, OWN_SUBSCRIPTION_HOST, OWN_RULES_URL } from "../src/worker.js";

const token = "A".repeat(43);
async function fixture() {
  return {
    schema: 1,
    entry: { host: "notes.nikcode.xyz", port: 443, naive: { username: "test", password: "test-secret" }, vless: { uuid: "22222222-2222-4222-8222-222222222222", public_key: "public-test-key", short_id: "abcdef12", server_name: "www.google.com" } },
    subscriptions: [{ hash: await tokenHash(token), enabled: true, format: "sing-box", formats: ["sing-box", "outbounds", "throne", "hiddify", "incy"] }],
  };
}
async function call(path, config, method = "GET") {
  return worker.fetch(new Request("https://config.nikcode.xyz" + path, { method }), { SERVICE_CONFIG: JSON.stringify(config) });
}

const pilotToken = "p_" + "C".repeat(43);
async function pilotFixture() {
  return { schema: 1, magic_dns_suffix: "example.ts.net", nodes: [
    { id: "france", enabled: true, protocol: "vless", host: "192.0.2.1", port: 443, server_name: "example.com", public_key: "A".repeat(43), short_id: "abcd" },
    { id: "frankfurt", enabled: true, protocol: "vless", host: "192.0.2.2", port: 34443, server_name: "example.com", public_key: "B".repeat(43), short_id: "abcd" },
  ], devices: [
    { id: "nik-iphone-primary", enabled: true, tailscale: true, hash: await tokenHash(pilotToken), credentials: {
      france: { uuid: "11111111-1111-4111-8111-111111111111" }, frankfurt: { uuid: "22222222-2222-4222-8222-222222222222" },
    } },
    { id: "nik-iphone-spare", enabled: true, tailscale: true, hash: await tokenHash("p_" + "D".repeat(43)), credentials: {
      france: { uuid: "33333333-3333-4333-8333-333333333333" }, frankfurt: { uuid: "44444444-4444-4444-8444-444444444444" },
    } },
  ] };
}
const sixDeviceTokens = [..."CDEFGH"].map((letter) => "p_" + letter.repeat(43));
async function fourNodeSixDeviceFixture() {
  const config = await pilotFixture();
  config.subscription_hosts = ["config.nikcode.xyz", OWN_SUBSCRIPTION_HOST];
  config.rules_url = OWN_RULES_URL;
  config.nodes.push(
    { id: "poland", enabled: true, protocol: "vless", host: "192.0.2.3", port: 443, server_name: "example.com", public_key: "E".repeat(43), short_id: "abcd" },
    { id: "italy", enabled: true, protocol: "vless", host: "192.0.2.4", port: 443, server_name: "example.com", public_key: "F".repeat(43), short_id: "abcd" },
  );
  for (const id of ["nik-galaxy-s22", "goar-iphone-primary", "goar-iphone-second", "andrey-maksimov-iphone"]) {
    config.devices.push({ id, enabled: true, tailscale: id === "nik-galaxy-s22",
      hash: await tokenHash(sixDeviceTokens[config.devices.length]), credentials: {} });
  }
  for (const [index, device] of config.devices.entries()) {
    device.rule_set_mode = index === 2 ? "remote" : "inline";
    for (const [offset, node] of config.nodes.entries()) {
      device.credentials[node.id] ??= { uuid: "00000000-0000-4000-8000-" + String(index * 4 + offset + 1).padStart(12, "0") };
    }
  }
  return config;
}
async function pilotCall(path, config, legacy = undefined) {
  return worker.fetch(new Request("https://config.nikcode.xyz" + path), {
    ...(legacy ? { SERVICE_CONFIG: JSON.stringify(legacy) } : {}), PILOT_CONFIG: JSON.stringify(config),
  });
}

test("pilot credentials are isolated per device and node without legacy secrets", async () => {
  const config = await pilotFixture();
  assert.equal(validPilot(config), true);
  const response = await pilotCall("/s/" + pilotToken, config);
  assert.equal(response.status, 200);
  const profile = await response.json();
  assert.deepEqual(profile.outbounds.filter((o) => o.type === "vless").map((o) => o.uuid),
    Object.values(config.devices[0].credentials).map((c) => c.uuid));
  assert.doesNotMatch(JSON.stringify(profile), /33333333|44444444|test-secret|notes.nikcode.xyz/);
  const spare = await (await pilotCall("/s/p_" + "D".repeat(43), config)).json();
  assert.notEqual(profile.endpoints[0].state_directory, spare.endpoints[0].state_directory);
});

test("six devices retain inline, remote and Tailscale shape when the equal VPN pool expands to four nodes", async () => {
  const config = await fourNodeSixDeviceFixture();
  const unchanged = structuredClone(config);
  const before = structuredClone(config);
  before.nodes = before.nodes.slice(0, 2);
  for (const device of before.devices) {
    delete device.credentials.poland;
    delete device.credentials.italy;
  }
  assert.equal(validPilot(config), true);
  assert.equal(new Set(config.devices.flatMap((device) => Object.values(device.credentials).map((c) => c.uuid))).size, 24);
  for (const [index, device] of config.devices.entries()) {
    const path = "/s/" + sixDeviceTokens[index];
    const response = await pilotCall(path, config);
    assert.equal(response.status, 200);
    const body = await response.text();
    assert.equal(await (await pilotCall(path, config)).text(), body);
    assert.equal(await (await pilotCall(path + "/sing-box-ios", config)).text(), body);
    const profile = JSON.parse(body);
    assert.equal(profile.route.final, "proxy");
    assert.deepEqual(profile.outbounds[0], {
      type: "urltest", tag: "proxy", outbounds: ["france", "frankfurt", "poland", "italy"],
      url: "https://www.gstatic.com/generate_204", interval: "1m", tolerance: 100, interrupt_exist_connections: false,
    });
    assert.deepEqual(profile.outbounds.filter((o) => o.type === "vless").map((o) => o.uuid),
      [device.credentials.france.uuid, device.credentials.frankfurt.uuid, device.credentials.poland.uuid, device.credentials.italy.uuid]);
    assert.equal(profile.route.rule_set[0].type, index === 2 ? "remote" : "inline");
    if (index === 2) {
      assert.equal(profile.route.rule_set[0].url, OWN_RULES_URL);
      assert.deepEqual(profile.route.rule_set[0].http_client, { engine: "go", detour: "direct" });
    } else {
      assert.ok(profile.route.rule_set[0].rules[0].ip_cidr.length > 10000);
    }
    assert.equal(profile.experimental.cache_file.cache_id, device.id);
    if (index < 3) {
      assert.equal(profile.endpoints[0].hostname, device.id);
      assert.equal(profile.endpoints[0].state_directory, "tailscale-" + device.id);
      assert.equal(profile.endpoints[0].auth_key, undefined);
    } else {
      assert.equal(profile.endpoints, undefined);
      assert.equal(profile.dns.servers.some((server) => server.type === "tailscale"), false);
      assert.equal(profile.route.rules.some((rule) => rule.outbound === "ts-ep"), false);
    }
    const previous = await (await pilotCall(path, before)).json();
    // Only the new pool members, their VLESS outbounds and bootstrap names may differ.
    const normalized = structuredClone(profile);
    normalized.outbounds = normalized.outbounds.filter((o) => !["poland", "italy"].includes(o.tag));
    normalized.outbounds[0].outbounds = ["france", "frankfurt"];
    const bootstrap = normalized.dns.rules.find((rule) => rule.domain?.includes("config.nikcode.xyz"));
    bootstrap.domain = bootstrap.domain.filter((host) => !["192.0.2.3", "192.0.2.4"].includes(host));
    assert.deepEqual(normalized, previous);
  }
  assert.deepEqual(config, unchanged);
});

test("revoked, invalid and unknown pilots never use the legacy catalog", async () => {
  const config = await fourNodeSixDeviceFixture();
  const legacy = await fixture();
  legacy.subscriptions[0].hash = config.devices[0].hash;
  config.devices[0].enabled = false;
  assert.equal((await pilotCall("/s/" + pilotToken, config, legacy)).status, 404);
  assert.equal((await pilotCall("/s/p_" + "Z".repeat(43), config, legacy)).status, 404);
  assert.equal((await pilotCall("/s/" + pilotToken, {}, legacy)).status, 503);
  assert.equal((await pilotCall("/s/" + pilotToken, { ...config, nodes: [null, null] }, legacy)).status, 503);
  config.devices[0].enabled = true;
  for (const [deviceIndex, nodeId, otherIndex, otherNodeId] of [
    [0, "france", 1, "france"], [5, "italy", 0, "france"], [2, "poland", 2, "frankfurt"],
  ]) {
    const duplicate = structuredClone(config);
    duplicate.devices[deviceIndex].credentials[nodeId].uuid = duplicate.devices[otherIndex].credentials[otherNodeId].uuid;
    assert.equal((await pilotCall("/s/" + pilotToken, duplicate, legacy)).status, 503);
    duplicate.nodes.find((node) => node.id === nodeId).enabled = false;
    assert.equal((await pilotCall("/s/" + pilotToken, duplicate, legacy)).status, 503);
  }
});

test("pilot pool never includes DIRECT and disabled nodes cannot enter a new profile", async () => {
  const config = await fourNodeSixDeviceFixture();
  const profile = singBoxPilot(config, config.devices[0]);
  assert.equal(profile.route.final, "proxy");
  const pool = profile.outbounds.find((o) => o.tag === "proxy");
  assert.equal(pool.type, "urltest");
  assert.deepEqual(pool.outbounds, ["france", "frankfurt", "poland", "italy"]);
  assert.equal(pool.interval, "1m");
  assert.equal(pool.tolerance, 100);
  assert.equal(pool.interrupt_exist_connections, false);
  config.nodes[2].enabled = false;
  const withoutPoland = await (await pilotCall("/s/" + pilotToken, config)).json();
  assert.deepEqual(withoutPoland.outbounds[0].outbounds, ["france", "frankfurt", "italy"]);
  assert.equal(withoutPoland.outbounds.some((o) => o.tag === "poland"), false);
  assert.doesNotMatch(JSON.stringify(withoutPoland), /192\.0\.2\.3/);
  assert.ok(!JSON.stringify(withoutPoland).includes(config.devices[0].credentials.poland.uuid));
  for (const node of config.nodes) node.enabled = false;
  assert.equal((await pilotCall("/s/" + pilotToken, config)).status, 503);
});

test("thin pilot keeps routing and identity while only replacing the inline rule set", async () => {
  const config = await pilotFixture();
  const fullBody = await (await pilotCall("/s/" + pilotToken, config)).text();
  const otherBefore = await (await pilotCall("/s/p_" + "D".repeat(43), config)).text();
  config.devices[0].rule_set_mode = "inline";
  assert.equal(await (await pilotCall("/s/" + pilotToken, config)).text(), fullBody);
  config.devices[0].rule_set_mode = "remote";
  const response = await pilotCall("/s/" + pilotToken, config);
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.ok(new TextEncoder().encode(body).length < 8192);
  const thin = JSON.parse(body);
  const full = JSON.parse(fullBody);
  const rules = thin.route.rule_set;
  assert.equal(rules[0].type, "remote");
  assert.match(rules[0].url, /^https:\/\/raw\.githubusercontent\.com\/SagerNet\/sing-geoip\/[a-f0-9]{40}\/geoip-ru\.srs$/);
  assert.deepEqual(rules[0].http_client, { engine: "go", detour: "proxy" });
  assert.equal(rules[0].download_detour, undefined);
  assert.equal(thin.experimental.cache_file.enabled, true);
  assert.equal(thin.experimental.cache_file.cache_id, config.devices[0].id);
  thin.route.rule_set = full.route.rule_set;
  assert.deepEqual(thin, full);
  assert.equal(await (await pilotCall("/s/p_" + "D".repeat(43), config)).text(), otherBefore);
  config.devices[0].rule_set_mode = "unsupported";
  assert.equal((await pilotCall("/s/" + pilotToken, config)).status, 503);
});

test("pilot subscription HTTPS and bootstrap DNS bypass failed pool narrowly", async () => {
  const config = await pilotFixture();
  const profile = singBoxPilot(config, config.devices[0]);
  const direct = profile.route.rules.find((r) => r.domain?.includes("config.nikcode.xyz"));
  assert.deepEqual(direct, { domain: ["config.nikcode.xyz"], network: "tcp", port: [443], action: "route", outbound: "direct" });
  assert.equal(profile.dns.rules.find((r) => r.domain?.includes("config.nikcode.xyz")).server, "bootstrap");
  assert.equal(profile.dns.servers.find((s) => s.tag === "bootstrap").detour, "direct");
  assert.equal(profile.dns.servers.find((s) => s.tag === "remote").detour, "proxy");
  assert.ok(profile.route.rules.some((r) => r.rule_set?.includes("geoip-ru") && r.outbound === "direct"));
});

test("integrated tailnet routing and MagicDNS precede private DIRECT and public AAAA policy", async () => {
  const config = await pilotFixture();
  const profile = singBoxPilot(config, config.devices[0]);
  const tail = profile.route.rules.findIndex((r) => r.ip_cidr?.includes("100.64.0.0/10"));
  const privateRule = profile.route.rules.findIndex((r) => r.ip_is_private);
  assert.ok(tail < privateRule);
  assert.equal(profile.route.rules[tail].outbound, "ts-ep");
  assert.equal(profile.dns.rules[0].preferred_by, "ts-dns");
  assert.equal(profile.dns.rules[1].domain_suffix[0], "example.ts.net");
  assert.equal(profile.endpoints[0].auth_key, undefined);
  assert.equal(profile.endpoints[0].accept_routes, false);
  assert.equal(profile.endpoints[0].system_interface, false);
  assert.equal(profile.endpoints[0].domain_resolver, "bootstrap");
  assert.equal(profile.inbounds[0].stack, "gvisor");
  assert.ok(profile.dns.rules.findIndex((r) => r.server === "local") < profile.dns.rules.findIndex((r) => r.query_type?.includes("AAAA")));
  assert.equal(profile.route.rule_set[0].type, "inline");
  assert.ok(profile.route.rule_set[0].rules[0].ip_cidr.length > 10000);
});

test("optional pilot binding leaves every legacy response byte identical", async () => {
  const legacy = await fixture();
  for (const binding of [await pilotFixture(), {}, null]) {
    for (const format of legacy.subscriptions[0].formats) {
      const path = "/s/" + token + "/" + format;
      const before = await call(path, legacy);
      const after = await pilotCall(path, binding, legacy);
      assert.equal(after.status, before.status);
      assert.equal(await after.text(), await before.text());
    }
  }
});

test("owned-host options are strict and preserve narrow bootstrap and DIRECT exceptions", async () => {
  const config = await pilotFixture();
  config.subscription_hosts = ["config.nikcode.xyz", OWN_SUBSCRIPTION_HOST];
  config.rules_url = OWN_RULES_URL;
  config.devices[0].rule_set_mode = "remote";
  assert.equal(validPilot(config), true);
  const response = await pilotCall("/s/" + pilotToken, config);
  const body = await response.text();
  assert.ok(new TextEncoder().encode(body).length < 8192);
  const profile = JSON.parse(body);
  assert.equal(profile.route.rule_set[0].url, OWN_RULES_URL);
  assert.deepEqual(profile.route.rule_set[0].http_client, { engine: "go", detour: "direct" });
  assert.equal(profile.outbounds.find((outbound) => outbound.tag === "direct").domain_resolver, "bootstrap");
  assert.ok(profile.dns.rules.some((r) => r.domain?.includes(OWN_SUBSCRIPTION_HOST) && r.server === "bootstrap"));
  assert.deepEqual(profile.route.rules.find((r) => r.domain?.includes(OWN_SUBSCRIPTION_HOST)), {
    domain: ["config.nikcode.xyz", OWN_SUBSCRIPTION_HOST], network: "tcp", port: [443], action: "route", outbound: "direct",
  });
  for (const hosts of [["untrusted.example"], [OWN_SUBSCRIPTION_HOST, OWN_SUBSCRIPTION_HOST], ["https://" + OWN_SUBSCRIPTION_HOST], []]) {
    assert.equal(validPilot({ ...config, subscription_hosts: hosts }), false);
  }
  for (const url of ["http://" + OWN_SUBSCRIPTION_HOST + "/rules/test.srs", OWN_RULES_URL + "?token=secret", OWN_RULES_URL.replace(OWN_SUBSCRIPTION_HOST, "untrusted.example")]) {
    assert.equal(validPilot({ ...config, rules_url: url }), false);
  }
});

test("Cloudflare redirect is confined to pilot paths and an exact owned HTTPS origin", async () => {
  const legacy = await fixture();
  const origin = "https://" + OWN_SUBSCRIPTION_HOST;
  const env = { SERVICE_CONFIG: JSON.stringify(legacy), PILOT_ORIGIN: origin };
  for (const suffix of ["", "/sing-box-ios"]) {
    const path = "/s/" + pilotToken + suffix;
    for (const method of ["GET", "HEAD"]) {
      const response = await worker.fetch(new Request("https://config.nikcode.xyz" + path, { method }), env);
      assert.equal(response.status, 307);
      assert.equal(response.headers.get("location"), origin + path);
      assert.match(response.headers.get("cache-control"), /no-store/);
      assert.equal(await response.text(), "");
    }
  }
  for (const format of legacy.subscriptions[0].formats) {
    const path = "/s/" + token + "/" + format;
    const before = await call(path, legacy);
    const after = await worker.fetch(new Request("https://config.nikcode.xyz" + path), env);
    assert.equal(after.status, before.status);
    assert.equal(after.headers.get("location"), null);
    assert.equal(await after.text(), await before.text());
  }
  for (const path of ["/s/" + pilotToken + "?anything=1", "/s/" + pilotToken + "/incy", "/s/p_short"]) {
    assert.equal((await worker.fetch(new Request("https://config.nikcode.xyz" + path), env)).headers.get("location"), null);
  }
  for (const invalid of ["http://" + OWN_SUBSCRIPTION_HOST, origin + "/", origin + ":443", "https://untrusted.example", "https://user@" + OWN_SUBSCRIPTION_HOST]) {
    assert.equal((await worker.fetch(new Request("https://config.nikcode.xyz/s/" + pilotToken), { PILOT_ORIGIN: invalid })).status, 503);
  }
});

test("unauthorized_or_revoked_subscription_shouldNotDiscloseCredentials", async () => {
  const config = await fixture();
  for (const path of ["/s/" + "B".repeat(43), "/s/short", "/s/" + token + "?format=incy"]) {
    const response = await call(path, config);
    assert.equal(response.status, 404);
    assert.equal(await response.text(), "Not found\n");
  }
  config.subscriptions[0].enabled = false;
  assert.equal((await call("/s/" + token, config)).status, 404);
});

test("valid_subscription_shouldUseStableDomainsAndNoDeviceSpecificInterface", async () => {
  const response = await call("/s/" + token, await fixture());
  assert.equal(response.status, 200);
  assert.match(response.headers.get("cache-control"), /no-store/);
  const profile = await response.json();
  assert.equal(profile.route.final, "proxy");
  for (const outbound of profile.outbounds.filter((o) => ["naive", "vless"].includes(o.type))) {
    assert.equal(outbound.server, "notes.nikcode.xyz");
    assert.equal(outbound.bind_interface, undefined);
    assert.equal(outbound.domain_resolver, "bootstrap");
  }
  assert.equal(profile.outbounds.find((o) => o.type === "naive").tls.server_name, "notes.nikcode.xyz");
  assert.equal(profile.outbounds.find((o) => o.type === "vless").tls.server_name, "www.google.com");
});

test("client_specific_export_shouldRetainProtocolAndTlsParameters", async () => {
  const config = await fixture();
  const incy = await (await call("/s/" + token + "/incy", config)).text();
  assert.match(incy, /^vless:\/\//);
  assert.doesNotMatch(incy, /naive/);
  const uri = new URL(incy.trim());
  assert.equal(uri.hostname, "notes.nikcode.xyz");
  assert.equal(uri.searchParams.get("security"), "reality");
  assert.equal(uri.searchParams.get("pbk"), config.entry.vless.public_key);
  const throne = await (await call("/s/" + token + "/throne", config)).text();
  assert.match(throne, /^naive\+https:\/\//);
  assert.equal(throne.trim().split("\n").length, 2);
  const hiddify = await (await call("/s/" + token + "/hiddify", config)).json();
  assert.equal(hiddify.inbounds, undefined);
  assert.equal(hiddify.outbounds.filter((o) => o.type === "naive").length, 1);
});

test("happ_mobile_subscription_shouldUseFirefoxAndRetainOtherClientFingerprints", async () => {
  const config = await fixture();
  config.subscriptions[0].formats.push("happ");
  const response = await call("/s/" + token + "/happ", config);
  assert.equal(response.status, 200);
  const link = new URL((await response.text()).trim());
  assert.equal(link.searchParams.get("fp"), "firefox");
  assert.equal(link.hostname, "notes.nikcode.xyz");
  assert.equal(link.searchParams.get("security"), "reality");
  assert.equal(link.searchParams.get("pbk"), config.entry.vless.public_key);
  const incy = new URL((await (await call("/s/" + token + "/incy", config)).text()).trim());
  assert.equal(incy.searchParams.get("fp"), "chrome");
  const generic = await (await call("/s/" + token, config)).json();
  assert.equal(generic.outbounds.find((o) => o.type === "vless").tls.utls.fingerprint, "chrome");
});

test("device_fingerprint_override_shouldSurviveRefreshWithoutChangingOtherSubscriptions", async () => {
  const config = await fixture();
  const otherToken = "B".repeat(43);
  config.subscriptions.push({ ...config.subscriptions[0], hash: await tokenHash(otherToken) });
  config.subscriptions[0].vless_fingerprint = "firefox";
  const sameLink = "/s/" + token + "/incy";
  for (let refresh = 0; refresh < 2; refresh++) {
    const response = await call(sameLink, config);
    assert.equal(response.status, 200);
    const uri = new URL((await response.text()).trim());
    assert.equal(uri.searchParams.get("fp"), "firefox");
  }
  const other = new URL((await (await call("/s/" + otherToken + "/incy", config)).text()).trim());
  assert.equal(other.searchParams.get("fp"), "chrome");
  const profile = await (await call("/s/" + token, config)).json();
  assert.equal(profile.outbounds.find((o) => o.type === "vless").tls.utls.fingerprint, "firefox");
  assert.equal(config.entry.vless.fingerprint, undefined);
  config.subscriptions[0].vless_fingerprint = "unsupported";
  assert.equal((await call(sameLink, config)).status, 503);
});

test("ios_pilot_subscription_shouldOfferNaiveWithoutDesktopDnsOrLegacyFields", async () => {
  const config = await fixture();
  const before = structuredClone(config.entry);
  Object.assign(config.subscriptions[0], {
    format: "sing-box-ios", formats: ["sing-box-ios"], vless_fingerprint: "firefox",
  });
  for (const suffix of ["", "/sing-box-ios"]) {
    const response = await call("/s/" + token + suffix, config);
    assert.equal(response.status, 200);
    const profile = await response.json();
    const naive = profile.outbounds.find((o) => o.type === "naive");
    assert.equal(naive.server, "notes.nikcode.xyz");
    assert.equal(naive.tls.server_name, naive.server);
    assert.equal(profile.outbounds.find((o) => o.type === "selector").default, naive.tag);
    assert.equal(profile.outbounds.find((o) => o.type === "vless").tls.utls.fingerprint, "firefox");
    assert.ok(profile.inbounds.some((i) => i.type === "tun"));
    assert.equal(profile.dns.servers.some((s) => s.server === "100.100.100.100" || s.address), false);
    assert.equal(profile.route.rule_set[0].download_detour, undefined);
    assert.equal(profile.route.rule_set[0].http_client.engine, "go");
    assert.equal(profile.route.rules.find((r) => r.network === "udp").outbound, "primary-vless");
    assert.equal(profile.experimental.cache_file.enabled, true);
  }
  assert.deepEqual(config.entry, before);
  assert.equal((await call("/s/" + token + "/incy", config)).status, 404);
});

test("subscription_service_shouldWorkWithoutContactingTheVpnServer", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("Origin must not be contacted"); };
  try {
    const config = await fixture();
    assert.equal((await call("/healthz", config)).status, 200);
    assert.equal((await call("/s/" + token, config)).status, 200);
  } finally { globalThis.fetch = previous; }
});

test("android_subscription_shouldUseNaiveForTcpAndRetainWorkingUdpAndDirectRoutes", async () => {
  const config = await fixture();
  Object.assign(config.subscriptions[0], {
    format: "sing-box-android", formats: ["sing-box-android"], vless_fingerprint: "firefox",
  });
  for (const suffix of ["", "/sing-box-android"]) {
    const response = await call("/s/" + token + suffix, config);
    assert.equal(response.status, 200);
    const profile = await response.json();
    assert.equal(profile.outbounds.find((o) => o.type === "selector").default, "primary-naive");
    assert.equal(profile.outbounds.find((o) => o.type === "vless").tls.utls.fingerprint, "firefox");
    assert.equal(profile.inbounds.find((i) => i.type === "tun").auto_route, true);
    assert.equal(profile.inbounds.find((i) => i.type === "tun").auto_redirect, undefined);
    assert.equal(profile.dns.servers.some((s) => s.tag === "tailscale"), false);
    assert.equal(profile.dns.servers.some((s) => s.bind_interface), false);
    const udpIndex = profile.route.rules.findIndex((r) => r.network === "udp");
    const russianIndex = profile.route.rules.findIndex((r) => r.rule_set?.includes("geoip-ru"));
    assert.ok(russianIndex < udpIndex);
    assert.equal(profile.route.rules[udpIndex].outbound, "primary-vless");
    assert.equal(profile.route.rules.find((r) => r.domain_suffix?.includes("google.com")).network, "tcp");
    assert.equal(profile.route.rules.find((r) => r.ip_is_private).outbound, "direct");
    assert.equal(profile.experimental.cache_file.enabled, true);
  }
});

test("malformed_service_configuration_shouldFailClosed", async () => {
  const response = await call("/s/" + token, {});
  assert.equal(response.status, 503);
  assert.doesNotMatch(await response.text(), /secret|uuid|password/);
});

test("head_or_public_page_shouldNotLeakSubscriptionSecrets", async () => {
  const config = await fixture();
  const head = await call("/s/" + token, config, "HEAD");
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
  const page = await (await call("/", config)).text();
  assert.doesNotMatch(page, /test-secret|22222222|\/s\//);
  assert.doesNotMatch(page, /VPN|подписк|приложени|подключени|sing-box|Throne|Hiddify|Incy/i);
  assert.equal((await call("/s/" + token, config, "POST")).status, 405);
});

test("mac_subscription_shouldCaptureSystemTrafficAndKeepPrivateRoutes", async () => {
  const config = await fixture();
  config.subscriptions[0].format = "sing-box-macos";
  config.subscriptions[0].formats = ["sing-box-macos"];
  const response = await call("/s/" + token, config);
  assert.equal(response.status, 200);
  const profile = await response.json();
  const tun = profile.inbounds.find((i) => i.type === "tun");
  assert.equal(tun.auto_route, true);
  assert.equal(tun.interface_name, undefined);
  assert.ok(tun.route_exclude_address.includes("192.168.0.0/16"));
  assert.ok(tun.route_exclude_address.includes("100.64.0.0/10"));
  assert.equal(profile.outbounds.find((o) => o.type === "selector").default, "primary-naive");
  assert.equal(profile.route.rules.find((r) => r.network === "udp").outbound, "primary-vless");
  assert.equal(profile.route.rules.find((r) => r.ip_is_private).outbound, "direct");
  const google = profile.route.rules.findIndex((r) => r.domain_suffix?.includes("google.com"));
  const russian = profile.route.rules.findIndex((r) => r.rule_set?.includes("geoip-ru"));
  assert.ok(google < russian);
  assert.equal(profile.route.rules[google].outbound, "proxy");
  assert.equal(profile.dns.rules.find((r) => r.domain_suffix?.includes("ts.net")).server, "tailscale");
  // 1.14 rejects DNS detours through an otherwise empty direct outbound.
  assert.equal(profile.dns.servers.find((s) => s.tag === "bootstrap").detour, undefined);
  assert.equal(profile.dns.servers.find((s) => s.tag === "tailscale").detour, undefined);
  assert.equal(profile.route.rule_set[0].download_detour, undefined);
  assert.equal(profile.route.rule_set[0].http_client.detour, "proxy");
  assert.equal((await call("/s/" + token + "/incy", config)).status, 404);
  assert.doesNotMatch(JSON.stringify(profile), /148\.253\.212\.96|en0|wlo1/);
});

test("legacy_ios_subscription_shouldUse111DnsAndVlessWithoutModernFields", async () => {
  const config = await fixture();
  config.subscriptions[0].format = "sing-box-ios-legacy";
  config.subscriptions[0].formats = ["sing-box-ios-legacy"];
  const response = await call("/s/" + token, config);
  assert.equal(response.status, 200);
  const profile = await response.json();
  assert.ok(profile.inbounds.some((i) => i.type === "tun" && i.auto_route));
  assert.equal(profile.outbounds.find((o) => o.tag === "proxy").type, "vless");
  assert.equal(profile.outbounds.find((o) => o.tag === "proxy").server, "notes.nikcode.xyz");
  assert.equal(profile.outbounds.find((o) => o.tag === "proxy").domain_strategy, "ipv4_only");
  assert.equal(profile.dns.servers[0].address, "https://1.1.1.1/dns-query");
  assert.equal(profile.dns.servers[0].type, undefined);
  assert.equal(profile.route.rules.find((r) => r.ip_is_private).outbound, "direct");
  const body = JSON.stringify(profile);
  assert.doesNotMatch(body, /domain_resolver|http_client|primary-naive|test-secret|148\.253\.212\.96/);
  assert.equal((await call("/s/" + token + "/sing-box", config)).status, 404);
});

test("linux_subscription_shouldKeepTailnetDnsAndRouteGoogleUdpToVless", async () => {
  const config = await fixture();
  const profile = singBoxLinux(config);
  const tun = profile.inbounds.find((i) => i.type === "tun");
  assert.equal(tun.interface_name, "nekoray-tun");
  assert.equal(tun.auto_redirect, true);
  assert.equal(profile.dns.servers.find((s) => s.tag === "tailscale").bind_interface, "tailscale0");
  assert.equal(profile.route.rules.find((r) => r.process_name?.includes("tailscaled")).outbound, "direct");
  assert.equal(profile.route.rules.find((r) => r.domain_suffix?.includes("google.com")).network, "tcp");
  assert.equal(profile.route.rules.find((r) => r.network === "udp").outbound, "primary-vless");
  assert.doesNotMatch(JSON.stringify(profile), /wlp3s0|wlo1|148\.253\.212\.96/);
  config.subscriptions[0].format = "sing-box-linux";
  config.subscriptions[0].formats = ["sing-box-linux"];
  const response = await call("/s/" + token, config);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), profile);
});

test("all_full_profiles_shouldReturnEmptyPublicAAAAAndRejectPublicIPv6BeforeRoutingExceptions", async () => {
  const config = await fixture();
  for (const format of ["sing-box", "hiddify", "sing-box-macos", "sing-box-linux", "sing-box-android", "sing-box-ios", "sing-box-ios-legacy"]) {
    const profile = JSON.parse(render(config, format).body);
    const aaaaIndex = profile.dns.rules.findIndex((rule) => rule.query_type?.includes("AAAA"));
    assert.ok(aaaaIndex >= 0, format + " must explicitly handle AAAA");
    const aaaa = profile.dns.rules[aaaaIndex];
    if (format === "sing-box-ios-legacy") {
      assert.equal(aaaa.action, "route");
      assert.equal(profile.dns.servers.find((server) => server.tag === aaaa.server).address, "rcode://success");
      assert.equal(aaaa.disable_cache, true);
      assert.ok(aaaaIndex < profile.dns.rules.findIndex((rule) => rule.outbound === "any"));
      assert.doesNotMatch(JSON.stringify(profile), /predefined|"rcode"|domain_resolver|http_client/);
    } else {
      assert.equal(aaaa.action, "predefined", format);
      assert.equal(aaaa.rcode, "NOERROR", format);
      assert.equal(aaaa.answer?.length || 0, 0, format);
    }
    assert.equal(profile.dns.rules.some((rule) => rule.action === "reject"), false, format + " must not return REFUSED");
    const privateIndex = profile.route.rules.findIndex((rule) => rule.ip_is_private);
    const rejectIndex = profile.route.rules.findIndex((rule) => rule.ip_version === 6);
    assert.ok(privateIndex >= 0 && rejectIndex > privateIndex, format + " must keep private IPv6 direct");
    assert.equal(profile.route.rules[privateIndex].outbound, "direct", format);
    const multicastIndex = profile.route.rules.findIndex((rule) => rule.ip_cidr?.includes("ff00::/8"));
    assert.ok(multicastIndex >= 0 && multicastIndex < rejectIndex, format + " must keep IPv6 multicast direct");
    assert.equal(profile.route.rules[multicastIndex].outbound, "direct", format);
    assert.deepEqual(profile.route.rules[rejectIndex], { ip_version: 6, action: "reject", method: "default", no_drop: true }, format);
    for (const [index, rule] of profile.route.rules.entries()) {
      if (rule.domain_suffix || rule.rule_set || rule.network === "udp") {
        assert.ok(rejectIndex < index, format + " must reject public IPv6 before public routing exceptions");
      }
    }
    assert.equal(profile.route.final, "proxy", format + " must not fall back direct");
  }
});

test("desktop_tailnet_AAAA_exception_shouldPrecedePublicSuppressionWithoutGlobalIPv4Only", async () => {
  const config = await fixture();
  for (const format of ["sing-box-macos", "sing-box-linux"]) {
    const profile = JSON.parse(render(config, format).body);
    const tailnetIndex = profile.dns.rules.findIndex((rule) => rule.domain_suffix?.includes("ts.net"));
    const aaaaIndex = profile.dns.rules.findIndex((rule) => rule.query_type?.includes("AAAA"));
    assert.ok(tailnetIndex >= 0 && tailnetIndex < aaaaIndex, format);
    assert.equal(profile.dns.rules[tailnetIndex].server, "tailscale", format);
    assert.equal(profile.dns.strategy, "prefer_ipv4", format);
    assert.equal(profile.dns.rules[tailnetIndex].strategy, undefined, format + " must avoid removed legacy rule strategy");
    assert.equal(profile.dns.servers.find((server) => server.tag === "tailscale").server, "100.100.100.100", format);
    const excluded = profile.inbounds.find((inbound) => inbound.type === "tun").route_exclude_address;
    for (const cidr of ["::1/128", "fc00::/7", "fe80::/10", "ff00::/8"]) assert.ok(excluded.includes(cidr), format + " " + cidr);
  }
  assert.ok(JSON.parse(render(config, "sing-box-ios-legacy").body).inbounds.find((inbound) => inbound.type === "tun").route_exclude_address.includes("ff00::/8"));
});

test("mobile_profiles_shouldRetainPublicAAAAHandlingWithoutADesktopTailnetResolver", async () => {
  const config = await fixture();
  for (const format of ["sing-box-android", "sing-box-ios"]) {
    const profile = JSON.parse(render(config, format).body);
    assert.equal(profile.dns.rules.some((rule) => rule.query_type?.includes("AAAA") && rule.action === "predefined"), true, format);
    assert.equal(profile.dns.rules.some((rule) => rule.server === "tailscale"), false, format);
    assert.equal(profile.dns.servers.some((server) => server.tag === "tailscale"), false, format);
  }
});

test("qr_share_shouldServeExactImageWithoutCachingAndSupportHead", async () => {
  const config = await fixture();
  const png = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const share = { path: "/qr/test-share1.png", expires: Date.now() + 60000, subscription_hash: config.subscriptions[0].hash, png: btoa(String.fromCharCode(...png)) };
  const env = { SERVICE_CONFIG: JSON.stringify(config), QR_SHARE: JSON.stringify(share) };
  const response = await worker.fetch(new Request("https://config.nikcode.xyz" + share.path), env);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "image/png");
  assert.match(response.headers.get("cache-control"), /no-store/);
  assert.match(response.headers.get("x-robots-tag"), /noindex/);
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), png);
  const head = await worker.fetch(new Request("https://config.nikcode.xyz" + share.path, { method: "HEAD" }), env);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
});

test("qr_share_shouldRejectExpiredRevokedUnknownAndMalformedShares", async () => {
  const config = await fixture();
  const share = { path: "/qr/test-share1.png", expires: Date.now() + 60000, subscription_hash: config.subscriptions[0].hash, png: "iVBORw0KGgo=" };
  const cases = [
    [share.path, undefined, config],
    [share.path, "{", config],
    ["/qr/other-share.png", JSON.stringify(share), config],
    [share.path + "?x=1", JSON.stringify(share), config],
    [share.path, JSON.stringify({ ...share, expires: Date.now() - 1 }), config],
    [share.path, JSON.stringify(share), { ...config, subscriptions: [{ ...config.subscriptions[0], enabled: false }] }],
  ];
  for (const [path, binding, state] of cases) {
    const response = await worker.fetch(new Request("https://config.nikcode.xyz" + path), { SERVICE_CONFIG: JSON.stringify(state), QR_SHARE: binding });
    assert.equal(response.status, 404);
    assert.equal(await response.text(), "Not found\n");
  }
});
