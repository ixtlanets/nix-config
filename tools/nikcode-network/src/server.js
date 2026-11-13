import { createServer } from "node:http";
import { lstat, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import worker, {
  HOST, OWN_SUBSCRIPTION_HOST, OWN_RULES_URL, PILOT_PATH,
  PILOT_RULES_BYTES, PILOT_RULES_PATH, PILOT_RULES_SHA256, validPilot,
} from "./worker.js";

// TLS belongs to the HTTPS reverse proxy. This process never listens publicly
// or logs request paths, bearer tokens, headers, profiles or configuration.
const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0", "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow, noarchive",
};

async function loadConfig(path) {
  const stat = await lstat(path);
  if (!stat.isFile() || (stat.mode & 0o037) !== 0 || stat.size > 5000) throw new Error("Private configuration unavailable");
  const raw = await readFile(path, "utf8");
  const config = JSON.parse(raw);
  if (!validPilot(config) || !config.subscription_hosts?.includes(OWN_SUBSCRIPTION_HOST)
    || config.rules_url !== OWN_RULES_URL || config.devices.some((device) => "token" in device)) {
    throw new Error("Private configuration unavailable");
  }
  return raw;
}

export async function createPilotServer({ configPath, rulesPath }) {
  const rules = await readFile(rulesPath);
  if (rules.length !== PILOT_RULES_BYTES || createHash("sha256").update(rules).digest("hex") !== PILOT_RULES_SHA256) {
    throw new Error("Pinned public rule set verification failed");
  }
  return createServer(async (request, response) => {
    const reply = (status, body, headers = {}) => {
      const bytes = Buffer.isBuffer(body) ? body : Buffer.from(body);
      response.writeHead(status, { ...PRIVATE_HEADERS, "Content-Type": "text/plain; charset=utf-8", ...headers,
        ...(status === 304 ? {} : { "Content-Length": bytes.length }) });
      response.end(request.method === "HEAD" || status === 304 ? undefined : bytes);
    };
    try {
      const host = request.headers.host?.toLowerCase();
      const loopbackHost = "127.0.0.1:" + request.socket.localPort;
      if (![OWN_SUBSCRIPTION_HOST, OWN_SUBSCRIPTION_HOST + ":443", loopbackHost].includes(host)
        || !request.url?.startsWith("/") || request.url.startsWith("//")) return reply(404, "Not found\n");
      if (!["GET", "HEAD"].includes(request.method)) return reply(405, "Method not allowed\n", { Allow: "GET, HEAD" });
      const url = new URL(request.url, "https://" + HOST);
      if (url.search) return reply(404, "Not found\n");
      if (url.pathname === PILOT_RULES_PATH) {
        const headers = { "Content-Type": "application/octet-stream", "Cache-Control": "public, max-age=31536000, immutable",
          ETag: '"' + PILOT_RULES_SHA256 + '"', "X-Content-SHA256": PILOT_RULES_SHA256 };
        return request.headers["if-none-match"] === headers.ETag ? reply(304, "", headers) : reply(200, rules, headers);
      }
      if (url.pathname !== "/healthz" && !PILOT_PATH.test(url.pathname)) return reply(404, "Not found\n");
      const config = await loadConfig(configPath);
      if (url.pathname === "/healthz") return reply(200, '{"status":"ok","service":"subscriptions"}\n', { "Content-Type": "application/json; charset=utf-8" });
      // Only the pilot renderer receives the canonical URL. No legacy catalog or
      // PILOT_ORIGIN is provided, so there is neither legacy access nor a loop.
      const rendered = await worker.fetch(new Request(url, { method: "GET" }), { PILOT_CONFIG: config });
      return reply(rendered.status, Buffer.from(await rendered.arrayBuffer()), Object.fromEntries(rendered.headers));
    } catch {
      return reply(503, "Service unavailable\n");
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [configPath, rulesPath, portText = "8787"] = process.argv.slice(2);
  const port = Number(portText);
  try {
    if (!configPath || !rulesPath || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid startup configuration");
    const server = await createPilotServer({ configPath, rulesPath });
    server.on("error", () => { process.stderr.write("Subscription listener failed\n"); process.exit(1); });
    server.listen(port, "127.0.0.1", () => process.stdout.write("Subscription listener ready on loopback\n"));
    for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => server.close(() => process.exit(0)));
  } catch {
    process.stderr.write("Subscription startup failed; check private configuration and pinned public rules\n");
    process.exitCode = 1;
  }
}
