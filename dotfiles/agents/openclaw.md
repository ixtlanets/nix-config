## OpenClaw

Use native `sessions_spawn` with `model: "fast"` or `model: "deep"` and
`context: "isolated"` for bounded child work. Aliases and default child thinking
come from the application configuration. Keep ordinary
helpers under the current agent; select another `agentId` only when its distinct
role is required. Pass the working directory and task restrictions explicitly.
Ordinary helpers return results to their parent; use visible persistent sessions
only when the user requests a separate session.
