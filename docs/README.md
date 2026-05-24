# Tank — documentation

> Tank is a local-first, privacy-preserving onboarding partner for new
> Sr/Staff/Manager security engineers. Reads your employer's docs +
> repos, redacts sensitive identifiers locally, and acts as a daily
> companion across your tenure.

This is the deep-dive documentation. For a quick start, the
top-level [README.md](../README.md) is faster to scan.

---

## Map of these docs

| File | What's in it |
| --- | --- |
| [installation.md](installation.md) | Local laptop install, dev-VM install, systemd unit, SSH tunnel setup |
| [first-run.md](first-run.md) | The 5-step conversational onboarding walkthrough |
| [using-tank.md](using-tank.md) | Day-to-day workflows for a security engineer |
| [architecture.md](architecture.md) | Internals: the three big subsystems, privacy contract, data model |
| [features/README.md](features/README.md) | Index of every feature page, grouped by phase |
| [operations.md](operations.md) | Running Tank on a dev VM: backups, healthz, scheduler, time zones |
| [faq.md](faq.md) | Common questions |
| [troubleshooting.md](troubleshooting.md) | Known issues and fixes |
| [images/](images/README.md) | Where to drop screenshots when you take them |

---

## What Tank is, in one screen

Tank takes the corpus your employer hands you on day one — architecture
docs, source repos, CMDB, org charts, runbooks, postmortems — and
turns it into:

1. **A typed knowledge graph** (Services, Repos, People, DataStores,
   Vendors, Controls, Policies, Runbooks, IAM policies, Detections,
   ATT&CK techniques) you can chat with.
2. **A set of generators** for the artifacts you'd otherwise hand-write
   weekly: threat models (versioned, drift-aware), design reviews,
   postmortems, tabletop exercises, on-call handoff briefs, weekly
   security digests.
3. **A daily companion**: morning digest, evening journal prompt,
   Friday weekly reflection, anniversary retrospectives. Tone shifts
   automatically with your tenure: **map → prioritize → execute →
   maintain**.
4. **A second brain**: lessons-learned DB, glossary of company jargon,
   personal ownership dashboard with per-entity risk scoring, and a
   curated security-philosophy document Tank helps evolve over time.

Everything runs locally. Internal hostnames, IPs, emails, AWS account
IDs, GCP projects, Azure subscriptions, secret tokens, and (optionally)
person names are redacted on your machine **before** anything reaches
the Claude API. The redaction map stays on the host.

> ⬜ **Screenshot placeholder**: home dashboard.
> Save as `images/today-dashboard.png` before pushing.
>
> ![Tank home dashboard](images/today-dashboard.png)

---

## Why "Tank"?

Tank in *The Matrix* was the crew's operator — the person on the
outside feeding context, maps, and answers to the team in the field.
That's the role for a new security hire's first 90 days: making sense
of an unfamiliar terrain fast enough to be useful.

---

## Project status

Tank ships in phases. The current state:

| Phase | What | Status |
| --- | --- | --- |
| 1 | Skeleton, DB schema, config, start.sh, README | ✅ |
| 2 | Redaction engine + 28/28 unit tests | ✅ |
| 2.5 | Helix Robotics sample data pack (26 files, 2 repos, full parser coverage) | ✅ |
| 3 | Ingestion pipeline (parse → chunk → redact → embed → store) | ✅ |
| 4 | KB layer (hybrid retrieval + 6 chat tools) | ✅ |
| 5 | Remaining parsers (DOCX, vision, CSV, repo summary) | ✅ |
| 6 | Chat with SSE streaming + tool use | ✅ |
| 7 | Six original reports (cached scope) | ✅ |
| 8 | Partner mode (digest, journal, follow-ups, anniversary) | ✅ |
| 9 | UI polish (entity graph, settings, badges) | ✅ |
| 10 | Privacy assertion script | ✅ |
| 11 | Opt-in connectors (folder, ICS, CVE, GitHub) | ✅ |
| 12 | Living threat models + decisions log | ✅ |
| 13 | Workstreams (design reviews, postmortems, tabletops, on-call, weekly digest) | ✅ |
| 14 | Coverage + visibility (Sigma, IAM, compliance, attack surface, ATT&CK mapping) | ✅ |
| 15 | Continuous learning (lessons, glossary, ownership, philosophy) | ✅ |
| Ops | systemd, healthz, weekly backup, retries, durable scheduler state | ✅ |
| UI  | Nyx theme + day/night toggle | ✅ |

For the change history with tradeoffs and known gaps, see
[HISTORY.md](../HISTORY.md).

---

## License

TBD — see the top-level [README.md](../README.md) for the current
status.
