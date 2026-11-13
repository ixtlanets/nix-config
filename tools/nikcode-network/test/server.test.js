import test from "node:test";
import assert from "node:assert/strict";
import { request as httpRequest } from "node:http";
import { mkdtemp, writeFile, chmod, rm, readFile, rename } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { createPilotServer } from "../src/server.js";
import { tokenHash, OWN_SUBSCRIPTION_HOST, OWN_RULES_URL, PILOT_RULES_PATH, PILOT_RULES_SHA256, PILOT_RULES_BYTES } from "../src/worker.js";

const token = "p_" + "S".repeat(43);
const rulesPath = fileURLToPath(new URL("../data/geoip-ru.srs", import.meta.url));

async function fixture() {
  return { schema: 1, magic_dns_suffix: "example.ts.net",
    subscription_hosts: ["config.nikcode.xyz", OWN_SUBSCRIPTION_HOST], rules_url: OWN_RULES_URL,
    nodes: [
      { id: "france", enabled: true, protocol: "vless", host: "192.0.2.1", port: 443, server_name: "example.com", public_key: "A".repeat(43), short_id: "abcd" },
      { id: "frankfurt", enabled: true, protocol: "vless", host: "192.0.2.2", port: 34443, server_name: "example.com", public_key: "B".repeat(43), short_id: "abcd" },
    ], devices: [{ id: "nik-galaxy-s22", enabled: true, tailscale: true, hash: await tokenHash(token), rule_set_mode: "remote",
      credentials: { france: { uuid: "11111111-1111-4111-8111-111111111111" }, frankfurt: { uuid: "22222222-2222-4222-8222-222222222222" } } }],
  };
}

function request(server, path, { method = "GET", host = OWN_SUBSCRIPTION_HOST, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = httpRequest({ hostname: "127.0.0.1", port: server.address().port, path, method,
      headers: { Host: host, ...headers }, agent: false }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks) }));
    });
    req.on("error", reject);
    req.end();
  });
}

async function setup(t, { missing = false } = {}) {
  const directory = await mkdtemp(join(tmpdir(), "nikcode-adapter-"));
  const configPath = join(directory, "pilot.json");
  const config = await fixture();
  if (!missing) await writeFile(configPath, JSON.stringify(config), { mode: 0o640 });
  const server = await createPilotServer({ configPath, rulesPath });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(async () => { await new Promise((resolve) => server.close(resolve)); await rm(directory, { recursive: true }); });
  return { directory, configPath, config, server };
}

test("own adapter authenticates pilot over HTTP and serves a thin full-policy profile", async (t) => {
  const { server, config } = await setup(t);
  assert.equal(server.address().address, "127.0.0.1");
  assert.equal((await request(server, "/healthz")).status, 200);
  const result = await request(server, "/s/" + token);
  assert.equal(result.status, 200);
  assert.ok(result.body.length < 8192);
  assert.equal(Number(result.headers["content-length"]), result.body.length);
  assert.match(result.headers["cache-control"], /no-store/);
  const profile = JSON.parse(result.body);
  assert.equal(profile.route.rule_set[0].url, OWN_RULES_URL);
  assert.equal(profile.route.rule_set[0].http_client.detour, "direct");
  assert.equal(profile.route.final, "proxy");
  assert.deepEqual(profile.outbounds.filter((o) => o.type === "vless").map((o) => o.uuid), Object.values(config.devices[0].credentials).map((c) => c.uuid));
  assert.deepEqual(profile.route.rules.find((rule) => rule.domain?.includes(OWN_SUBSCRIPTION_HOST)).domain, ["config.nikcode.xyz", OWN_SUBSCRIPTION_HOST]);
  const head = await request(server, "/s/" + token, { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.equal(head.body.length, 0);
  assert.equal(head.headers["content-length"], result.headers["content-length"]);
  for (const path of ["/s/p_" + "X".repeat(43), "/s/" + "A".repeat(43), "/s/" + token + "?token=test", "/qr/test.png"]) {
    assert.equal((await request(server, path)).status, 404);
  }
  assert.equal((await request(server, "/s/" + token, { host: "untrusted.example" })).status, 404);
  assert.equal((await request(server, "/s/" + token, { method: "POST" })).status, 405);
});

test("own adapter serves verified immutable rules with exact length, SHA and conditional HEAD", async (t) => {
  const { server } = await setup(t);
  const result = await request(server, PILOT_RULES_PATH);
  assert.equal(result.status, 200);
  assert.equal(result.body.length, PILOT_RULES_BYTES);
  assert.equal(Number(result.headers["content-length"]), PILOT_RULES_BYTES);
  assert.equal(createHash("sha256").update(result.body).digest("hex"), PILOT_RULES_SHA256);
  assert.match(result.headers["cache-control"], /immutable/);
  const head = await request(server, PILOT_RULES_PATH, { method: "HEAD" });
  assert.equal(head.body.length, 0);
  assert.equal(Number(head.headers["content-length"]), PILOT_RULES_BYTES);
  assert.equal((await request(server, PILOT_RULES_PATH, { headers: { "If-None-Match": result.headers.etag } })).status, 304);
  assert.equal((await request(server, PILOT_RULES_PATH + "?anything=1")).status, 404);
});

test("missing or unsafe private file fails closed; atomic replacement applies revocation without restart", async (t) => {
  const { server, directory, configPath, config } = await setup(t, { missing: true });
  assert.equal((await request(server, "/healthz")).status, 503);
  assert.equal((await request(server, "/s/" + token)).status, 503);
  assert.equal((await request(server, PILOT_RULES_PATH)).status, 200);
  await writeFile(configPath, JSON.stringify(config), { mode: 0o644 });
  await chmod(configPath, 0o644);
  assert.equal((await request(server, "/s/" + token)).status, 503);
  await chmod(configPath, 0o640);
  assert.equal((await request(server, "/s/" + token)).status, 200);
  config.devices[0].enabled = false;
  const next = join(directory, "next.json");
  await writeFile(next, JSON.stringify(config), { mode: 0o600 });
  await rename(next, configPath);
  assert.equal((await request(server, "/s/" + token)).status, 404);
  config.devices[0].token = token;
  await writeFile(configPath, JSON.stringify(config));
  assert.equal((await request(server, "/healthz")).status, 503);
});

test("rule-set startup rejects missing, truncated or corrupt public content", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "nikcode-rules-"));
  t.after(() => rm(directory, { recursive: true }));
  const path = join(directory, "rules.srs");
  await assert.rejects(createPilotServer({ configPath: "/unused", rulesPath: path }));
  await writeFile(path, "truncated");
  await assert.rejects(createPilotServer({ configPath: "/unused", rulesPath: path }), /verification failed/);
  const content = await readFile(rulesPath);
  content[content.length - 1] ^= 1;
  await writeFile(path, content);
  await assert.rejects(createPilotServer({ configPath: "/unused", rulesPath: path }), /verification failed/);
});
