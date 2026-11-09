## DSH delegation and project routing

Before selecting a child model or passing data to a child, read the applicable
project instructions and the documents they require for this type of work.
Determine the permitted providers, models, data-processing routes and context
scope. Project requirements override the default fast/deep routes below, subject
to higher-priority instructions. Distinguish the agent's model from a processing
model called by a project tool: selecting an agent never grants permission to
send restricted source material to its provider.

If a required route is unavailable, pause the dependent work and report why.
Do not substitute another route without the corresponding authorization.

### Default routes

These defaults are rendered from `nix-config/dotfiles/agents/routes.json`; fast
and deep are task classes, not named DSH agents or tool aliases.

{{routes}}

Before the first explicit model choice in a task, use `list_subagent_models` to
check provider/model ids and reasoning levels actually permitted in this session.
If a configured default cannot be matched, report it and pause the dependent
model choice rather than silently falling back. If the project permits model
choice, escalate fast's material uncertainty to deep with the evidence and the
specific unresolved question, retaining the project's data restrictions.

### Native tools and inherited configuration

Follow the current native DSH instructions when choosing subagent, fork or team
mechanisms. Specify a model only when the current tool schema supports it;
otherwise check the inherited model against project requirements before dispatch.
Children inherit the parent's preset unless explicitly assigned another one;
changing a model does not relax the project's restrictions. Do not assume every
parent agent-local tool restriction is cloned: check the applicable child
permission policy and explicitly pass task restrictions, including discussion or
planning mode, with the minimum necessary context and bounded assignment.
Do not create extra agent identities merely to perform ordinary helper work.
