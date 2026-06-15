# Tank

<p align="center"><img width="400" height="250" alt="tank" src="https://github.com/user-attachments/assets/ac7cc97d-2d5b-4ede-b795-7d506c2e5267"/></p>

A local-first security engineering partner for the first security hire. Tank asks you 20 questions about your company, seeds a knowledge graph from your answers, and generates a Day-1 Brief — before you upload a single document. Over 90 days it grows with you: threat models, risk register, policies, runbooks, and leadership-ready reports grounded in your actual environment.

**Nothing leaves your machine in cleartext.** Hostnames, emails, IPs, account IDs, and secrets are redacted locally before any Claude API call.

**Cost-conscious by default.** Prompt caching at every stable breakpoint (1h TTL on system + KB-scope blocks, 5m on per-turn retrieval), a Sonnet/Haiku split that routes structured-extraction work to the cheaper model, and Anthropic Message Batches (50% off) for every background scheduler job — auto-briefs, report subscriptions, anniversaries, and ATT&CK mapping all submit asynchronously and persist when results land.

---

## Features

- **Intake Interview** — 20 questions seed your entity graph and generate a Day-1 Brief with no documents needed
- **Org Discovery Wizard** — GitHub org scan, CSV team import, and manual service entry to build your asset inventory
- **Chat over your KB** — streaming chat with 15 tools; discovery mode when KB is sparse
- **Threat models + DFD analysis** — per-service STRIDE threat models with drift detection; 4-mode DFD input (paste Mermaid, upload `.mmd`/image, from document, from description); analyze ingested diagrams directly from the KB
- **Knowledge graph** — D3.js force-directed interactive graph across all entity types; pan/zoom, hover highlighting, click to navigate
- **Risk register + Prioritization Engine** — formal risk tracking with a concrete quarterly top-5 action plan
- **Security policies** — first-draft policies (AUP, IR, SDL, vuln management, data classification) using your actual stack
- **90-Day Plan** — week-by-week task list generated from your intake answers and KB
- **Leadership reports** — State of Security, Initial Assessment, Program Roadmap in plain business language; entity picker for scoped reports
- **Token usage dashboard** — per-source, per-model, per-call-site spend breakdown with 14-day history at `/usage`
- **Kanban boards** — multi-board drag-and-drop task tracking (TODO / Doing / Done) with inline card editing; boards per project or workstream at `/kanban`
- **Daily companion** — morning digest, nudges, journal, meeting prep, anniversary retros

---

## Quick start

```bash
git clone https://github.com/LeSpookyHacker/tank.git tank
cd tank
cp .env.example .env          # paste your ANTHROPIC_API_KEY
./scripts/start.sh            # creates .venv, installs deps, boots the server
```

Open `http://localhost:8000`. You'll complete a brief setup, then Tank walks you through the intake interview.

**Requirements:** Python 3.11+, an [Anthropic API key](https://console.anthropic.com/settings/keys).

---

## Try it with sample data

Tank ships with a complete **synthetic** company so you can explore every feature without exposing real data. You're cast as the **first Application Security hire at MedScribe-R-Us**, a GCP-based healthcare-AI startup (PHI, HIPAA, Vertex AI, FHIR/Epic-Cerner). The scenario is modeled on the public case study at [LeSpookyHacker/medscribe-r-us-appsec](https://github.com/LeSpookyHacker/medscribe-r-us-appsec); everything in `sample_data/` is fictional, with deliberately planted secrets and internal hostnames so you can watch redaction work.

```bash
python -m scripts._gen_fixtures            # render PDF/DOCX/PNG from Markdown
python -m scripts.load_fixtures            # ingest docs + 2 service repos (uses your API key)
python -m scripts.seed_db                  # living artifacts: risks, vulns, threat models, plan…
python -m scripts.verify_privacy --fixture-pack   # assert nothing leaked (exit 0 = pass)
```

See [sample_data/README.md](sample_data/README.md) for the full inventory.

---

## Documentation

| | |
|--|--|
| [Quickstart](docs/quickstart.md) | Running in under 10 minutes, top failure points |
| [First run](docs/first-run.md) | The intake interview and what happens after |
| [Features](docs/features/README.md) | Per-feature reference organized by nav group |
| [FAQ](docs/faq.md) | Common questions on privacy, cost, setup, daily use |
| [Configuration](docs/configuration.md) | All environment variables |
| [Using Tank](docs/using-tank.md) | Day-to-day workflows |
| [Installation](docs/installation.md) | VM setup, systemd, SSH tunnel |
| [Troubleshooting](docs/troubleshooting.md) | Things that go wrong at runtime |
| [Architecture](docs/architecture.md) | How it works internally |

---

## License

MIT — see [LICENSE](LICENSE).

---

## Contributing

Bug reports, docs improvements, and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, the privacy contract, and PR guidelines. Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.
