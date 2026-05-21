"""IAM policy parser (AWS, K8s RBAC, GCP IAM bindings).

Detection is content-based — we look at the JSON/YAML structure
rather than relying on extension alone. Each IAM policy becomes one
`IAMPolicy` entity. The chunk text contains a structured rendering
that's friendly to retrieval ("Policy X allows s3:* on *").

We compute a coarse risk_score (0-10) at parse time based on:
- wildcard actions (`*`, `*:*`)
- wildcard resources (`*`, ARNs ending in `:*`)
- missing MFA conditions on sensitive actions
- broad Principal in trust policies (`*` or `AWS:*`)
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class IAMParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        flavor, doc = self._detect_and_load(raw)
        title = path.stem
        risk_score, callouts = 0.0, []
        rendered_blocks: list[str] = []

        if flavor == "aws_policy":
            risk_score, callouts = self._score_aws_policy(doc)
            rendered_blocks.append(self._render_aws_policy(doc))
        elif flavor == "k8s_rbac":
            risk_score, callouts = self._score_k8s(doc)
            rendered_blocks.append(self._render_k8s(doc))
        elif flavor == "gcp_iam":
            risk_score, callouts = self._score_gcp(doc)
            rendered_blocks.append(self._render_gcp(doc))
        else:
            rendered_blocks.append(raw[:4000])

        meta = {
            "format": flavor,
            "risk_score": risk_score,
            "risk_callouts": callouts,
        }
        rendered = (
            f"# IAM Policy: {title}\n\n"
            f"**Risk score:** {risk_score:.1f}/10\n\n"
            + ("\n".join(f"- {c}" for c in callouts) if callouts else "_no callouts_")
            + "\n\n"
            + "\n\n".join(rendered_blocks)
        )
        return ParsedDocument(
            kind="iam", title=title,
            sections=[ParsedSection(section_path="policy", text=rendered)],
            meta=meta,
        )

    def _detect_and_load(self, raw: str) -> tuple[str, dict | list]:
        # Try JSON first; YAML fall-back lives in the bare text path.
        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                doc = json.loads(stripped)
            except Exception:
                doc = {}
        else:
            try:
                import yaml  # type: ignore
                doc = yaml.safe_load(stripped) or {}
            except Exception:
                doc = {}
        if isinstance(doc, dict):
            if "Statement" in doc or "Version" in doc:
                return ("aws_policy", doc)
            kind = (doc.get("kind") or "").lower()
            api = (doc.get("apiVersion") or "").lower()
            if "rbac" in api or kind in ("role", "clusterrole",
                                          "rolebinding", "clusterrolebinding"):
                return ("k8s_rbac", doc)
            if "bindings" in doc or "etag" in doc:
                return ("gcp_iam", doc)
        return ("unknown", doc if isinstance(doc, (dict, list)) else {})

    # ---- AWS ----

    def _score_aws_policy(self, doc: dict) -> tuple[float, list[str]]:
        score, callouts = 0.0, []
        statements = doc.get("Statement") or []
        if isinstance(statements, dict):
            statements = [statements]
        for s in statements:
            if not isinstance(s, dict):
                continue
            effect = s.get("Effect", "Allow")
            if effect != "Allow":
                continue
            actions = s.get("Action") or []
            if isinstance(actions, str):
                actions = [actions]
            resources = s.get("Resource") or []
            if isinstance(resources, str):
                resources = [resources]
            if any(a in ("*", "*:*") for a in actions):
                score += 5.0
                callouts.append("Wildcard action `*` granted")
            elif any(":*" in a for a in actions):
                score += 1.5
                callouts.append(f"Wildcard within service: {actions}")
            if any(r == "*" for r in resources):
                score += 3.0
                callouts.append("Resource `*` (any AWS resource)")
            elif any(r.endswith(":*") for r in resources):
                score += 1.0
                callouts.append("Resource ends in `:*` (broad)")
            cond = s.get("Condition") or {}
            sensitive = {"iam:passrole", "sts:assumerole",
                         "kms:decrypt", "s3:getobject"}
            if any(a.lower() in sensitive for a in actions if isinstance(a, str)):
                if not cond:
                    score += 0.5
                    callouts.append("Sensitive action without conditions")
            principal = s.get("Principal")
            if principal in ("*", {"AWS": "*"}):
                score += 4.0
                callouts.append("Principal `*` (anonymous)")
        return min(score, 10.0), callouts

    def _render_aws_policy(self, doc: dict) -> str:
        statements = doc.get("Statement") or []
        if isinstance(statements, dict):
            statements = [statements]
        lines = ["## Statements"]
        for i, s in enumerate(statements):
            if not isinstance(s, dict):
                continue
            lines.append(f"### {i + 1}. Effect={s.get('Effect', '?')}")
            actions = s.get("Action") or s.get("NotAction") or []
            if isinstance(actions, str):
                actions = [actions]
            resources = s.get("Resource") or s.get("NotResource") or []
            if isinstance(resources, str):
                resources = [resources]
            lines.append(f"- Actions: {', '.join(map(str, actions)) or '—'}")
            lines.append(f"- Resources: {', '.join(map(str, resources)) or '—'}")
            cond = s.get("Condition")
            if cond:
                lines.append(f"- Conditions: {json.dumps(cond)[:200]}")
            lines.append("")
        return "\n".join(lines)

    # ---- K8s RBAC ----

    def _score_k8s(self, doc: dict) -> tuple[float, list[str]]:
        score, callouts = 0.0, []
        rules = doc.get("rules") or []
        for r in rules:
            if not isinstance(r, dict):
                continue
            verbs = r.get("verbs") or []
            resources = r.get("resources") or []
            if "*" in verbs:
                score += 3.0
                callouts.append("Wildcard verb `*` in RBAC rule")
            if "*" in resources:
                score += 3.0
                callouts.append("Wildcard resource `*` in RBAC rule")
            if "secrets" in resources and \
                    any(v in verbs for v in ("get", "list", "*")):
                score += 2.0
                callouts.append("Secrets read access granted")
        kind = (doc.get("kind") or "").lower()
        if kind == "clusterrole":
            score += 1.0
            callouts.append("ClusterRole (cluster-wide scope)")
        return min(score, 10.0), callouts

    def _render_k8s(self, doc: dict) -> str:
        kind = doc.get("kind", "?")
        name = (doc.get("metadata") or {}).get("name", "?")
        rules = doc.get("rules") or []
        lines = [f"## {kind} `{name}`", ""]
        for r in rules:
            lines.append(f"- apiGroups: {r.get('apiGroups')} "
                         f"resources: {r.get('resources')} "
                         f"verbs: {r.get('verbs')}")
        return "\n".join(lines)

    # ---- GCP ----

    def _score_gcp(self, doc: dict) -> tuple[float, list[str]]:
        score, callouts = 0.0, []
        for b in doc.get("bindings") or []:
            if not isinstance(b, dict):
                continue
            role = b.get("role", "")
            members = b.get("members") or []
            if role in ("roles/owner", "roles/editor",
                        "roles/iam.securityAdmin"):
                score += 3.0
                callouts.append(f"Broad role granted: {role}")
            if "allUsers" in members or "allAuthenticatedUsers" in members:
                score += 4.0
                callouts.append("Bound to public principal (allUsers)")
        return min(score, 10.0), callouts

    def _render_gcp(self, doc: dict) -> str:
        lines = ["## Bindings"]
        for b in doc.get("bindings") or []:
            lines.append(f"- {b.get('role')} → {b.get('members')}")
        return "\n".join(lines)
