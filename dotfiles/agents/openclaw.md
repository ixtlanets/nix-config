## OpenClaw

Use native `sessions_spawn` with `model: "fast"` or `model: "deep"` and
`context: "isolated"` for bounded child work. Aliases and default child thinking
come from the application configuration. Keep ordinary
helpers under the current agent; select another `agentId` only when its distinct
role is required. Pass the working directory and task restrictions explicitly.
Ordinary helpers return results to their parent; use visible persistent sessions
only when the user requests a separate session.

### Knowledge base links

When citing a note from `/home/nik/vault`, give its title and a direct Indexary
link: `https://personal-openclaw.tailf108.ts.net/documents/<vault-relative-path>`.
Use the exact case and `.md` extension, percent-encode each UTF-8 path segment
separately, and keep the `/` separators. For example, `Notes/Next steps.md` becomes
`https://personal-openclaw.tailf108.ts.net/documents/Notes/Next%20steps.md`.
Link the root `index.md` to `https://personal-openclaw.tailf108.ts.net/`.
For a folder, use `/folders/<vault-relative-path>` on the same origin with the
same path encoding.
For attachments, link to the containing note and name the attachment. When a
direct attachment link is requested, use the material URL returned by Indexary
with the same HTTPS origin.

Indexary is private over Tailscale. Share these links only with authorized
recipients. If a note is unavailable in Indexary, give its vault-relative path
and say the link could not be verified.
