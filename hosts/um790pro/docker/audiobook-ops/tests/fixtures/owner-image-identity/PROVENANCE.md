# Offline image identity fixtures

The JSON files preserve raw bytes (including terminal newline, if any).
`container-identity-projection.json` and `image-projection.json` are the narrow,
nonsecret Go-template projections retained by the parent from the local daemon on
um790pro, Docker 29.9.2 with containerd storage, on 2026-11-04. They are NOT full
container/image metadata. No health output, environment or secrets were captured
in these fixtures. Original capture argv, exit 0 and SHA256 receipts are retained
in docker29-identity/container-identity-projection.receipt.json and
image-projection.receipt.json in the parent's task evidence.

`pinned-manifest.json` is the exact public OCI image manifest retained by the
parent in pinned-image-public/manifest.json, fetched for
`ghcr.io/flaresolverr/flaresolverr@sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa`.
Its raw SHA256 is that manifest digest; its byte length is 2572. Its config.digest
is sha256:894893ed4d4557764df3e74d27c5bc1b3944e5a33ed410e62ab7c744b348f415.
Tests validate raw bytes before parsing. This pinned public manifest establishes
the manifest-to-config relationship. Docker image inspect Descriptor does NOT
supply config.digest.

SHA256:

```
7758715b158796d49cbdfee8b724378d30a101c6d9d546755a7401846e2c184f  container-identity-projection.json
dd24599ec1364a0b2cb8805822c9bfab21fe0e8709f9789d6555d8a129c91d48  image-projection.json
258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa  pinned-manifest.json
```

The portable tests need no private evidence directory. They combine the narrow
production container projection with explicitly synthetic topology and Env from
the existing valid_inspect fixture; they do not claim full production metadata.
The classic config-ID image projection is synthetic: its proof comes from the
local daemon resolving the exact pinned RepoDigest to the config ID. A classic
Descriptor may be absent; if supplied it must describe the same pinned manifest.

The captured production projection used direct `.Descriptor` access because that
field exists on the observed Docker29/containerd image. The launcher's projection
uses `{{json (index . "Descriptor")}}` for the optional classic-store field. The
parent's separate read-only local cached-modern-image probes on 2026-11-04 found
missing direct map access fails, while map `index` returns JSON null (receipts
local-missing-field.receipt.json and local-missing-index.receipt.json in current
parent evidence). The portable argv assertion binds the transport to that exact
syntax; injected classic JSON does not independently execute a Go template or
prove behavior on a real classic daemon. The modern manifest-ID branch still
refuses missing/null Descriptor. The author made no Docker calls.
