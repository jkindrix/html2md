# ADR 0001: Defer scale-out crawling architecture

- Status: Accepted
- Date: 2026-07-16
- Decision owners: Project maintainers
- Scope: concurrency, scheduling/daemon mode, distributed workers, shared queues,
  databases/cloud storage, webhooks, metrics services, and dashboards

## Context

The historical roadmap proposed an enterprise distributed crawler, three cloud
storage backends, scheduling, monitoring, notifications, and a web dashboard in
approximately four weeks. It supplied estimates and aspirational availability
targets, but no observed user workloads, baseline benchmark, service-level
objective, deployment model, operating budget, or distributed-systems threat
model.

The stabilization review found the opposite immediate need: primary
single-process paths were broken while approximately 1,150 lines of unreachable
async concurrency code added defects and dependency cost. That stack was
removed. The resulting crawler deliberately performs one active request at a
time and now has tested robots, rate-limit, retry, checkpoint, interruption,
resume, output-containment, and failure contracts. The 0.1.0 alpha establishes a
reliable baseline; it does not establish demand for horizontal scale.

Repository evidence currently contains no real workload that misses a stated
throughput, latency, memory, cost, or availability target. Building a service
platform now would optimize an unmeasured problem and multiply the boundaries
that were just made dependable.

## Decision

Keep every capability in scope above deferred. None is an active roadmap item,
and the historical roadmap/work breakdown are not delivery commitments.

Scale work may be proposed only after a public 1.0 release and must satisfy all
entry gates below before implementation begins. Passing the gates authorizes an
architecture decision; it does not predetermine a distributed design.

### 1. Measured user need

A proposal must identify a real, reproducible workload and record:

- corpus ownership, size, page/host distribution, update frequency, and whether
  authenticated or JavaScript-rendered pages are involved;
- required completion time, maximum server request rate, peak memory/storage,
  reliability, recovery-time, and operating-cost targets;
- the measured single-process result on that workload; and
- why configuration, sequential checkpoints, multiple independent CLI jobs, or
  an external scheduler cannot meet the target safely.

Anonymous market comparisons and synthetic throughput alone do not satisfy this
gate.

### 2. Versioned benchmark

Add a reproducible benchmark corpus and harness before changing architecture.
At minimum it must report:

- pages/minute and end-to-end completion time by host count;
- request concurrency per origin and robots/rate-policy compliance;
- peak resident memory, state size, output bytes, and checkpoint latency;
- interruption recovery time, duplicate/lost work, and output equivalence;
- 429/5xx/error rates and retry amplification; and
- results at increasing corpus sizes until the stated target or a measured
  bottleneck is reached.

Baseline, candidate, Python/platform, commit, configuration, and raw results must
be retained. A candidate must preserve output and policy correctness, not merely
increase throughput.

### 3. Architecture decision

Write a new ADR comparing the smallest viable options in this order:

1. tune the sequential implementation;
2. bounded per-origin concurrency in one process;
3. independent process sharding with the existing durable state contract;
4. an external queue/orchestrator; and
5. a project-owned distributed service.

The ADR must define ownership, failure semantics, migration/rollback, operating
cost, observability, compatibility, and a removal plan. Distributed coordination
is acceptable only when simpler steps fail the measured target.

### 4. Resource and security model

Before implementation, document and test:

- global and per-origin request budgets, fairness, backpressure, cancellation,
  queue bounds, worker memory/CPU/disk limits, and retry storms;
- robots and rate-limit coordination across workers;
- delivery semantics, idempotent output/state commits, deduplication, leases,
  clock skew, partitions, worker loss, and disaster recovery;
- URL validation and SSRF controls at every producer, queue, redirect, browser,
  image, and webhook boundary;
- tenant/job authentication and authorization, secret/cookie isolation,
  encryption, log redaction, retention, deletion, and cloud-storage ACLs;
- dashboard/API session security, CSRF/CORS, audit logs, and administrative
  actions; and
- dependency, patching, deployment, monitoring, alerting, and cost ownership.

No dashboard, webhook, shared database, cloud SDK, broker, or coordinator is to
be added speculatively before its boundary is defined.

## Consequences

The project remains a lightweight local CLI with sequential crawling. Very large
jobs may take longer and users must use external scheduling or independent,
non-overlapping jobs when appropriate. In return, installation, operation,
failure recovery, and server politeness stay understandable and testable.

This decision can be superseded by a later ADR only when all four entry gates
have durable evidence. Until then, proposals in the historical roadmap are
explicitly non-goals rather than backlog items.
