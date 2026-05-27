"""Pydantic schemas for Tank.

These models are shared between the API surface, the storage layer, and the
Claude-side structured-output prompts. Keep them in one place so changes to
the data model are visible across every consumer.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------- enums ----------

class RoleMode(str, Enum):
    IC = "ic"
    MANAGER = "manager"
    BOTH = "both"


class Provenance(str, Enum):
    SOURCE = "source"        # directly from an ingested doc
    INFERRED = "inferred"    # Claude-derived w/ reasoning trace
    CLAIM = "claim"          # something a person said, unverified
    USER = "user"            # explicitly entered/confirmed by the user


EntityType = Literal[
    "Service", "Repo", "Person", "Endpoint", "DataStore",
    "CloudAccount", "Vendor", "Control", "Policy", "Runbook",
    # Phase 14 additions
    "Detection", "AttackTechnique", "IAMPolicy", "Asset",
]

RelationshipKind = Literal[
    "depends_on", "owns", "reports_to", "stores_data_in",
    "authenticates_via", "exposes", "hosted_in", "integrates_with",
    "has_control",
]

DocumentCategory = Literal["architecture", "code", "cmdb", "people_process"]

NudgeKind = Literal[
    "coverage_gap", "stale_context", "meeting_followthrough",
    "question_of_week", "pattern_detection", "reflection_prompt",
    "reading_queue", "contradiction",
]


# ---------- ingest ----------

class ExtractedEntity(BaseModel):
    """Claude-extracted entity from a chunk or diagram."""
    type: EntityType
    name: str
    description: str | None = None
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_quote: str | None = Field(
        default=None,
        description="One-sentence excerpt anchoring this extraction.",
    )


class ExtractedRelationship(BaseModel):
    src_name: str
    src_type: EntityType
    dst_name: str
    dst_type: EntityType
    kind: RelationshipKind
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ChunkExtraction(BaseModel):
    """Output schema for the generic chunk → entities/edges extractor."""
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class DiagramExtraction(BaseModel):
    """Output schema for the diagram → entities/edges vision extractor."""
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    diagram_summary: str | None = None


# ---------- chat ----------

class ChatMessageIn(BaseModel):
    content: str


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    section_path: str | None = None
    snippet: str


# ---------- redaction ----------

class RedactionMatch(BaseModel):
    """A single redaction performed during apply_redactions().

    Used by the engine to communicate what was replaced; never serialized
    over the wire to Claude (the placeholder shows up in the prompt; the
    map stays local).
    """
    category: str
    placeholder: str
    original: str
    occurrences: int = 1


class RedactionResult(BaseModel):
    redacted_text: str
    matches: list[RedactionMatch] = Field(default_factory=list)


class RedactionRule(BaseModel):
    id: int | None = None
    category: str
    enabled: bool = True
    pattern: str | None = None
    placeholder_fmt: str | None = None
    description: str | None = None


# ---------- partner mode ----------

class NudgePayload(BaseModel):
    kind: NudgeKind
    title: str
    body: str
    payload: dict = Field(default_factory=dict)
    priority: int = 50


class MeetingPrepRequest(BaseModel):
    who: str
    when: str | None = None
    extra_context: str | None = None


class MeetingPrepBrief(BaseModel):
    who_summary: str
    their_world: str
    overlap: str
    unknowns: list[str]
    ranked_questions: list[dict]   # {"question": str, "why": str}
    one_thing_to_offer: str
    citations: list[Citation] = Field(default_factory=list)


class NotesIn(BaseModel):
    body: str
    meeting_with_entity_id: str | None = None


class NotesDiff(BaseModel):
    """Output of notes_to_kb extraction — proposed, not committed."""
    new_entities: list[ExtractedEntity] = Field(default_factory=list)
    new_relationships: list[ExtractedRelationship] = Field(default_factory=list)
    facts: list[dict] = Field(default_factory=list)


# ---------- app state ----------

class UserScope(BaseModel):
    """What the user told Tank during onboarding about their role."""
    domain: str | None = None
    org: str | None = None
    manager: str | None = None
    priorities: list[str] = Field(default_factory=list)
    freewrite: str | None = None


class AppState(BaseModel):
    role_mode: RoleMode = RoleMode.BOTH
    internal_tld: str | None = None
    user_scope: UserScope = Field(default_factory=UserScope)
    digest_time: str = "08:00"
    reflection_day: str = "fri"
    onboarded: bool = False
    tenure_started_at: float | None = None
    last_journal_at: float | None = None
    philosophy_doc_id: str | None = None


# ---------- reports ----------

class STRIDEThreat(BaseModel):
    stride_category: str    # 'Spoofing'|'Tampering'|'Repudiation'|'InfoDisclosure'|'DoS'|'EoP'
    title: str
    description: str
    likelihood: str         # 'low'|'medium'|'high'
    impact: str             # 'low'|'medium'|'high'
    suggested_controls: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class ThreatLandscapeReport(BaseModel):
    service_name: str
    threats: list[STRIDEThreat]
    summary: str
    blind_spots: list[str] = Field(default_factory=list)


class Gap(BaseModel):
    pattern: str
    affected_entity_ids: list[str] = Field(default_factory=list)
    affected_entity_names: list[str] = Field(default_factory=list)
    severity: str           # 'low'|'medium'|'high'|'critical'
    notes: str
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class CrossServiceGapsReport(BaseModel):
    gaps: list[Gap]
    blind_spots: list[str] = Field(default_factory=list)
    summary: str


class PlanAction(BaseModel):
    title: str
    why: str
    who_to_talk_to: list[str] = Field(default_factory=list)
    estimated_effort: str   # 'half-day'|'1-2 days'|'1 week'|'multi-week'
    success_signal: str


class PlanReport(BaseModel):
    day_30: list[PlanAction]
    day_60: list[PlanAction]
    day_90: list[PlanAction]
    rationale: str


class StakeholderTier(BaseModel):
    name: str
    role: str | None = None
    overlap_areas: list[str] = Field(default_factory=list)
    suggested_first_conversation: str | None = None


class StakeholderMap(BaseModel):
    critical: list[StakeholderTier]
    frequent: list[StakeholderTier]
    situational: list[StakeholderTier]
    first_30_day_intros: list[str] = Field(default_factory=list)
    summary: str


class QuestionList(BaseModel):
    team_or_person: str
    must_ask: list[str]
    should_ask: list[str]
    nice_to_ask: list[str]
    red_flags_to_probe: list[str] = Field(default_factory=list)


class ControlMatrixRow(BaseModel):
    service_name: str
    service_id: str | None = None
    controls: dict[str, str]   # control_name -> 'yes'|'partial'|'no'|'unknown'
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class ControlMatrix(BaseModel):
    rows: list[ControlMatrixRow]
    controls_checked: list[str]
    summary: str


# ---------- Day-1 brief, anniversary, journal ----------

class Day1BriefQuestion(BaseModel):
    question: str
    who_to_ask: str
    why_it_matters: str


class Day1BriefRead(BaseModel):
    title: str
    document_id: str | None = None
    why: str


class Day1BriefMeeting(BaseModel):
    who: str
    why: str
    suggested_when: str | None = None    # e.g. "week 1", "week 2"


class Day1Brief(BaseModel):
    scope_echo: str
    top_entities: list[dict]              # [{name, type, one_line}]
    week1_questions: list[Day1BriefQuestion]
    week1_reading: list[Day1BriefRead]
    week1_meetings: list[Day1BriefMeeting]


class AnniversaryRetro(BaseModel):
    day_n: int
    what_you_built: list[str]
    what_you_learned: list[str]
    what_drifted: list[str]
    next_30_days: list[str]
    summary: str


# ---------- Phase 12: living threat models + decisions ----------

class ThreatV2(BaseModel):
    """A threat in a versioned threat model. Extends STRIDEThreat with
    drift markers so a re-generation can mark prior threats as
    still_valid / invalidated / new."""
    stride_category: str
    title: str
    description: str
    likelihood: str           # low|medium|high
    impact: str               # low|medium|high
    suggested_controls: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    state: str = "new"        # new|still_valid|invalidated|updated
    prior_threat_index: int | None = None  # if updated/still_valid


class ThreatModelV2(BaseModel):
    service_name: str
    service_id: str | None = None
    threats: list[ThreatV2]
    summary: str
    blind_spots: list[str] = Field(default_factory=list)
    invalidated_prior_titles: list[str] = Field(default_factory=list)


class ExtractedDecision(BaseModel):
    title: str
    body: str
    kind: str                     # design_choice|accepted_risk|deferred_fix|security_invariant
    rationale: str | None = None
    suggested_scope_entity_names: list[str] = Field(default_factory=list)
    suggested_expires_days: int | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class DecisionExtraction(BaseModel):
    decisions: list[ExtractedDecision] = Field(default_factory=list)


# ---------- Phase 13: workstream artifacts ----------

class DesignReviewChecklistItem(BaseModel):
    item: str
    checked: bool = False
    notes: str | None = None
    category: str | None = None    # authn|authz|crypto|data|deps|blast|logging|tm|rollout


class DesignReviewIntakePayload(BaseModel):
    """Sonnet's structured response when seeding a design review."""
    title: str
    scope_summary: str
    likely_risk_areas: list[str]
    missing_info: list[str]
    suggested_reviewers: list[str] = Field(default_factory=list)
    checklist: list[DesignReviewChecklistItem]


class PostmortemFields(BaseModel):
    summary: str
    timeline: list[str] = Field(default_factory=list)
    what_failed: str
    why: str
    contributing_factors: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class PostmortemDraftPayload(BaseModel):
    """Sonnet drafts these fields from a user freewrite."""
    title: str
    fields: PostmortemFields
    services_affected: list[str] = Field(default_factory=list)
    severity_guess: str | None = None  # sev1|sev2|sev3


class TabletopInject(BaseModel):
    minute: int
    inject: str
    expected_response: str | None = None


class TabletopScenario(BaseModel):
    title: str
    scenario_md: str
    injects: list[TabletopInject]
    facilitation_notes: str
    evaluation_rubric: list[str]


class OnCallHandoff(BaseModel):
    service_name: str
    open_action_items: list[str] = Field(default_factory=list)
    recent_incidents: list[str] = Field(default_factory=list)
    new_threats: list[str] = Field(default_factory=list)
    deploy_freeze: str | None = None
    on_call_now: str | None = None
    notes: str


class WeeklyDigestSection(BaseModel):
    title: str
    bullets: list[str]


class WeeklySecurityDigest(BaseModel):
    week_label: str
    sections: list[WeeklyDigestSection]
    one_thing_to_focus: str


# ---------- Phase 14: coverage + visibility ----------

class AttackMappingRow(BaseModel):
    service_name: str
    tactic: str
    technique_id: str             # e.g. T1078
    technique_name: str
    exposure: str                 # high|medium|low
    detections: list[str] = Field(default_factory=list)   # detection names covering


class AttackMappingReport(BaseModel):
    rows: list[AttackMappingRow]
    coverage_summary: str
    top_gaps: list[str] = Field(default_factory=list)


class IAMPolicyRisk(BaseModel):
    policy_name: str
    policy_id: str | None = None
    risks: list[str]              # human-readable callouts
    score: float                  # 0-10 risk
    explanation_md: str


class IAMAuditReport(BaseModel):
    policies: list[IAMPolicyRisk]
    summary: str
    top_risks: list[str] = Field(default_factory=list)


class EvidenceMatch(BaseModel):
    control_id: str
    control_title: str
    evidence_kind: str             # document|decision|policy|runbook|threat_model
    evidence_id: str
    evidence_title: str
    confidence: float


class ComplianceEvidenceMap(BaseModel):
    matches: list[EvidenceMatch]
    controls_with_no_evidence: list[str] = Field(default_factory=list)
    summary: str


# ---------- Phase 15: lessons, glossary, philosophy ----------

class LessonExtracted(BaseModel):
    title: str
    body_md: str
    tags: list[str]
    scope_entity_names: list[str] = Field(default_factory=list)


class LessonExtraction(BaseModel):
    lessons: list[LessonExtracted] = Field(default_factory=list)


class GlossaryCandidate(BaseModel):
    term: str
    definition: str
    aliases: list[str] = Field(default_factory=list)


class GlossaryExtraction(BaseModel):
    candidates: list[GlossaryCandidate] = Field(default_factory=list)


class PhilosophyStance(BaseModel):
    title: str
    body_md: str
    related_decision_ids: list[str] = Field(default_factory=list)


class PhilosophyDoc(BaseModel):
    intro: str
    stances: list[PhilosophyStance]
    open_questions: list[str] = Field(default_factory=list)


# ---------- DFD Threat Modeling (STRIDE) ----------

class DFDElement(BaseModel):
    id: str
    kind: str  # process | datastore | external_entity | dataflow | trust_boundary
    label: str


class DFDThreat(BaseModel):
    """STRIDE threat from DFD analysis. Severity must be Critical|High|Medium|Low."""
    threat_id: str                        # sequential: T001, T002, …
    element_id: str
    element_label: str
    stride_category: str                  # Spoofing|Tampering|Repudiation|Information Disclosure|Denial of Service|Elevation of Privilege
    severity: str                         # Critical|High|Medium|Low
    cvss_estimate: float | None = None
    title: str
    description: str
    mitigation: str
    references: list[str] = Field(default_factory=list)  # e.g. ["OWASP A02:2021", "CWE-347"]


class DFDAnalysis(BaseModel):
    elements: list[DFDElement] = Field(default_factory=list)
    threats: list[DFDThreat] = Field(default_factory=list)
    annotated_mermaid: str = ""


class DFDImprovement(BaseModel):
    improved_mermaid: str = ""
    suggestions: list[str] = Field(default_factory=list)


class DFDMermaidGeneration(BaseModel):
    """Mermaid DFD generated from a document or plain-language description."""
    mermaid: str = ""
    notes: list[str] = Field(default_factory=list)


# ---------- IR runbooks ----------

class IRRunbookPhase(BaseModel):
    phase: str          # detect|contain|eradicate|recover|comms
    steps: list[str] = Field(default_factory=list)
    decision_points: list[str] = Field(default_factory=list)
    time_box: str | None = None       # e.g. "first 15 minutes"
    success_criteria: str | None = None


class IRRunbookOutput(BaseModel):
    """Structured runbook generated by Sonnet."""
    title: str
    scenario_summary: str
    severity_trigger: str = "any"     # sev1|sev2|sev3|any
    detection_signals: list[str] = Field(default_factory=list)
    phases: list[IRRunbookPhase] = Field(default_factory=list)
    escalation_path: list[dict] = Field(default_factory=list)
      # [{role: str, trigger: str, channel: str}]
    comms_template: str | None = None


# ---------- Risk register ----------

class RiskAssessmentOutput(BaseModel):
    """Claude's assessment of a single risk entry."""
    residual_likelihood: int = Field(ge=1, le=5)
    residual_impact: int = Field(ge=1, le=5)
    assessment_summary: str
    recommended_treatment: str   # mitigate|accept|transfer|avoid
    treatment_rationale: str
    control_gaps: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)


class RiskRegisterReport(BaseModel):
    """Output for the risk_register report generator."""
    risks: list[dict]   # [{title, category, inherent_score, residual_score, treatment, owner}]
    summary: str
    top_risks: list[str] = Field(default_factory=list)
    control_coverage_notes: list[str] = Field(default_factory=list)


class VulnerabilityIntake(BaseModel):
    """Payload accepted by POST /api/vulnerabilities/intake (e.g. from Nyx)."""
    cve_id: str | None = None
    title: str
    description: str | None = None
    cvss_score: float | None = None
    cvss_vector: str | None = None
    severity: str = "medium"   # critical|high|medium|low|informational
    source: str = "manual"     # nvd|github_dependabot|scanner|manual|disclosure
    affected_service_names: list[str] = Field(default_factory=list)
    due_at: int | None = None
    external_ref: str | None = None


class SecurityProgramMetrics(BaseModel):
    """Aggregated metrics snapshot for the program health dashboard."""
    threat_models_total: int = 0
    threat_models_drifted: int = 0
    threat_models_updated_30d: int = 0
    vulns_open_critical: int = 0
    vulns_open_high: int = 0
    vulns_open_medium: int = 0
    vulns_open_low: int = 0
    vulns_avg_age_days: float = 0.0
    risks_open: int = 0
    risks_review_overdue: int = 0
    decisions_accepted_risk_open: int = 0
    decisions_expiring_30d: int = 0
    compliance_controls_total: int = 0
    compliance_controls_with_evidence: int = 0
    postmortems_published_90d: int = 0
    followups_open: int = 0
    followups_done_90d: int = 0
    design_reviews_open: int = 0
    design_reviews_approved_90d: int = 0
    snapshot_at: float = 0.0


class ExecutiveBriefOutput(BaseModel):
    """Claude's one-page executive security brief."""
    headline: str
    program_health: str        # green|yellow|red
    key_achievements: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    recommended_priorities: list[str] = Field(default_factory=list)
    summary_md: str


# ---------- Phase 13/14: additional NudgeKind values ----------
# (Kept as plain strings — NudgeKind Literal stays advisory; the DB
# accepts any string and the dispatch table is the source of truth.)
