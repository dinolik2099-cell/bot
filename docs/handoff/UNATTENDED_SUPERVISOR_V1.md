# Whole-Project Unattended Supervisor V1

The unattended supervisor is an independent, read-only control-plane observer.
Its default mode is `--once --shadow --json`; automatic recovery is disabled by
default and production deployment is intentionally outside this artifact.

It observes immutable historical identity artifacts, Forward/Demo checkpoints,
cross-chain plan identity, service metadata and host resources.  Identity,
authority, fail-closed and reconciliation ambiguity faults are `BLOCKED` and
are never repairable.  Only explicitly allowlisted Forward service/checkpoint
faults can become eligible for recovery after consecutive confirmation, a
cooldown/repair budget and an injected recovery adapter.

Runtime state is atomic and local-only under `server_local_audit/unattended/`.
It is ignored by Git and contains no credentials, endpoint query strings,
tokens, order requests or trading authority.  The proposed systemd unit/timer
are templates only; this change neither installs nor enables them.
