---
status: accepted
---

# Use a Hermes-facing audiobook control plane

Replace ReadMeABook with a repository-managed `audiobook-ops` control plane on
`um790pro`, exposed to the owner's existing Hermes profile through a narrow,
untrusted MCP interface. ReadMeABook's Audible-centric identity model does not
support reliable Russian discovery, while Hermes can resolve ambiguous works
and audio editions and the deterministic control plane can enforce approvals,
idempotency, filesystem containment, metadata revisions, and atomic publication.
Prowlarr, the RuTracker gateway, Transmission, the verified publisher,
Audiobookshelf, and Absorb remain; ReadMeABook, PostgreSQL, Redis, and their
application credentials are removed at the service cutover.

The trade-off is deliberate: the first version uses the owner's existing broad
Hermes profile rather than a separately isolated profile. The MCP server still
holds all upstream credentials on `um790pro`, exposes no raw upstream proxy or
arbitrary shell/path operation, and requires native Hermes approval for every
domain-changing `apply` operation.
