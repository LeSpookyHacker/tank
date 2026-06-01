# Screenshot manifest

This folder holds screenshots referenced from the other docs files.
Each placeholder in a doc is marked with `⬜ **Screenshot placeholder**`
and points to a filename inside this directory.

When you're ready to populate the docs with images, take a screenshot
of the corresponding Tank surface and save it under the matching
filename below.

## How to capture

- Use the **dark theme** by default — that's the brand. Optionally
  also capture **light theme** versions for the theme-toggle FAQ.
- Crop to the relevant area; don't include your browser chrome
  unless the URL bar is part of the point being made.
- Standard resolution: ~1400px wide. PNG. Reasonable file size
  (≤ 500KB each — `oxipng -o4` if you need to shrink).
- Anonymize: don't include real coworker names / hostnames / IPs.
  Use the MedScribe-R-Us sample data (`sample_data/`) as test data instead — it's
  synthetic by design.

## Filename list

Add the screenshots below to `docs/images/` with these exact names.
Each is referenced by a `![alt](images/<name>)` line somewhere in the
docs; the alt text in the docs tells you what the image should show.

### Top-level (docs/README.md)

- `today-dashboard.png` — home dashboard right after first ingest.

### Installation (docs/installation.md)

- `install-first-run-terminal.png` — terminal output of first
  `./scripts/start.sh`.
- `install-systemd-status.png` — `systemctl --user status tank`
  output.
- `install-ssh-tunnel-browser.png` — Tank running in your laptop
  browser via the SSH tunnel.

### Onboarding (docs/first-run.md)

- `onboarding-1-role.png` — role-pick step.
- `onboarding-2-scope.png` — scope-chips step with extracted fields.
- `onboarding-4-ingest.png` — ingest progress panel.
- `onboarding-5-day1-brief.png` — rendered Day-1 brief.

### Workflows (docs/using-tank.md)

- `workflow-morning-digest.png` — morning digest with 3 nudges.
- `workflow-design-review.png` — design review checklist mid-review.
- `workflow-tm-v2.png` — threat model v2 with state badges
  (✓ still_valid, ↻ updated, 🆕 new, ✗ invalidated).
- `workflow-anniversary.png` — Day-60 anniversary retro rendered.
- `workflow-chat-tools.png` — chat with tool-use trace expanded
  and citations visible.

### Architecture (docs/architecture.md)

- `arch-redaction-settings.png` — Settings page redaction categories
  with toggles + per-category match counts.

### Features

- `feature-chat-tools.png` — chat exchange with tool-use trace
  expanded and citations visible.
  *(referenced from features/chat-and-reports.md)*
- `feature-control-matrix.png` — control coverage matrix rendered.
  *(referenced from features/chat-and-reports.md)*
- `feature-threat-model-v2.png` — threat model detail with state
  badges on each threat.
  *(referenced from features/threat-models-decisions.md)*
- `feature-decisions-log.png` — decisions log filtered to
  `accepted_risk` with one entry expiring soon.
  *(referenced from features/threat-models-decisions.md)*
- `feature-design-review.png` — design review mid-checklist.
  *(referenced from features/workstreams.md)*
- `feature-postmortem-editor.png` — postmortem editor with
  structured fields filled.
  *(referenced from features/workstreams.md)*
- `feature-tabletop.png` — tabletop scenario page with injects +
  facilitation notes.
  *(referenced from features/workstreams.md)*
- `feature-weekly-digest.png` — weekly security digest rendered.
  *(referenced from features/workstreams.md)*
- `feature-detection-coverage.png` — detection coverage page
  showing covered vs uncovered techniques.
  *(referenced from features/coverage-visibility.md)*
- `feature-attack-mapping.png` — ATT&CK mapping report rendered.
  *(referenced from features/coverage-visibility.md)*
- `feature-iam-translator.png` — IAM policy explained in English.
  *(referenced from features/coverage-visibility.md)*
- `feature-compliance.png` — compliance page showing controls and
  gap badges.
  *(referenced from features/coverage-visibility.md)*
- `feature-attack-surface.png` — attack-surface page with latest
  snapshot + history.
  *(referenced from features/coverage-visibility.md)*
- `feature-lessons.png` — lessons page filtered by tag.
  *(referenced from features/second-brain.md)*
- `feature-ownership.png` — ownership dashboard with risk bars.
  *(referenced from features/second-brain.md)*
- `feature-glossary.png` — glossary page with pending + confirmed.
  *(referenced from features/second-brain.md)*
- `feature-philosophy.png` — philosophy doc rendered.
  *(referenced from features/second-brain.md)*

### Operations (docs/operations.md)

- `ops-backups.png` — backup directory listing.

## Optional extras (nice but not required)

- `theme-dark.png` and `theme-light.png` — side-by-side of the same
  page in both themes (for the day/night toggle FAQ).
- `entity-graph.png` — the entity graph viz at `/entities` rendering
  Service nodes with `depends_on` edges.
- `chat-mobile.png` — Tank in a narrow viewport (the layout is
  responsive but not optimized for mobile).
