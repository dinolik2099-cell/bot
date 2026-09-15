# Whole-Project Unattended Supervisor V1

The unattended supervisor is an independent, read-only control-plane observer.
Its default mode is `--once --shadow --json`; automatic recovery is disabled by
default and production deployment is intentionally outside this artifact.

It observes immutable historical identity artifacts and explicitly declared
current Forward/Demo production resources. Service working directories and data
roots are distinct. The JSON configuration declares each service, data root and
checkpoint so release/data epochs can change without source changes. A missing
or identity-invalid declared checkpoint is a resource configuration fault, not
a stale checkpoint and never repairable. Demo checkpoints are DEMO health
resources; they are not historical required artifacts.

It observes immutable historical identity artifacts, Forward/Demo checkpoints,
cross-chain plan identity, service metadata and host resources.  Identity,
authority, fail-closed and reconciliation ambiguity faults are `BLOCKED` and
are never repairable.  Only explicitly allowlisted Forward service/checkpoint
faults can become eligible for recovery after consecutive confirmation, a
cooldown/repair budget and an injected recovery adapter.

Runtime state is atomic and local-only under `runtime/unattended/`. This
gitignored project-local runtime directory is distinct from audit evidence;
the supervisor does not use `server_local_audit/` for its mutable state.
It is ignored by Git and contains no credentials, endpoint query strings,
tokens, order requests or trading authority.  The proposed systemd unit/timer
are templates only; this change neither installs nor enables them.

State mutation uses a local cross-process exclusive lock for the complete
read-modify-write transaction. Notification intents are durable `PENDING`
outbox entries and become `SENT` only after the sink returns successfully.
Delivery is recoverable at-least-once, not falsely claimed exactly-once.
Sent/recovered history has bounded retention while active issues and pending
notifications are retained. A time-window safety lock is never cleared
automatically; an operator may use the explicit `--once --rearm-repair-window`
command only when existing clock and repair evidence validate safely.
