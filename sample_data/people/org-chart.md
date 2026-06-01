# Org Chart — MedScribe-R-Us

```
Renee Tucker (CEO)
├── Aanya Krishnan (CTO)
│   ├── Dana Okafor (Staff SRE / Platform Lead)
│   │   └── Alex Kim (DevOps / SRE)
│   ├── Priya Raman (Pipeline Eng Lead)
│   │   ├── Sofia Castellano (Sr Eng, EMR Integration)
│   │   └── Hannah Osei (Eng, Transcription)
│   ├── Marcus Lee (AI Platform Lead)
│   │   └── Wei Chen (ML Eng, Scrubbing)
│   ├── Jordan Vale (Frontend Lead, Portals)
│   └── LeSpookyHacker (Staff AppSec Engineer)   ← you (first security hire)
└── Tom Bryce (IT / HIPAA Privacy Officer)
```

## Notes for the new security hire

- **Security has no team yet** — you are it. Build relationships with Dana
  (owns GCP/IAM), Marcus (owns the AI pipeline + scrubbing), and Tom (owns HIPAA
  compliance and BAAs).
- **Tier-0 services** (api-gateway, the full pipeline, EMR integration, portals)
  are owned across Platform / Pipeline / AI Platform / Frontend — no single
  owner has the whole picture. That's part of why you were hired.
- The **CTO (Aanya)** is your sponsor for getting CI security gates and the
  SOC 2 readiness work prioritized.
