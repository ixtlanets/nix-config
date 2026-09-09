# Personal Infrastructure

This repository describes and supports the hosts and services that make up the owner's personal infrastructure, including systems that are not yet fully managed by the repository.

## Language

**Private access path**:
A route through an authenticated private network that lets client devices reach a service without creating public ingress.
_Avoid_: Public endpoint, public proxy

**Service baseline**:
The verified user-visible behaviour of a service before a change, used as the acceptance contract for validation and rollback.
_Avoid_: Smoke test, current state

**Upgrade rehearsal**:
A parallel launch of a new service version against a consistent copy of its state, while the current instance remains untouched and available.
_Avoid_: Test upgrade, canary

**Pinned service image**:
A versioned OCI image whose platform-specific digest is recorded before deployment, so an update never depends on a moving tag such as `latest`.
_Avoid_: Latest image, fixed tag

**Consistent service snapshot**:
A copy of a service's database and adjacent persistent state taken at one logical moment while writers are stopped, suitable for rehearsal and rollback.
_Avoid_: File copy, database dump

**Service cutover**:
The controlled replacement of a live service endpoint with a rehearsed version using the latest production state, while retaining the previous container and a matching rollback snapshot.
_Avoid_: Deploy, promote rehearsal

## Omarchy Overlay

**Managed Omarchy configuration**:
A file under `dotfiles/omarchy/` that the repository installs into the user's live configuration. The repository copy is authoritative after an Omarchy refresh.
_Avoid_: Upstream default, live-only configuration

## Terminal Multiplexers

**Herdr session**:
A persistent Herdr server namespace. Normal project work shares the default session.
_Avoid_: Project, tmux session

**Workspace**:
The project-level Herdr container corresponding to a tmux session in the daily workflow.
_Avoid_: Herdr session

**Tab**:
A layout within a Herdr workspace, corresponding to a tmux window.
_Avoid_: Window

**Pane**:
A terminal region inside a Herdr tab or tmux window.
