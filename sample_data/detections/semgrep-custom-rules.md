# Custom Semgrep Rules — MedScribe-R-Us

Three custom SAST rules run in CI (`.github/workflows/sast.yml`) to catch the
healthcare-AI-specific footguns generic rulesets miss. They map to STRIDE
findings T-006 (PHI in logs) and T-007/T-014 (LLM output handling) and to the
"auth on every PHI endpoint" invariant.

## 1. `auth-missing` — PHI endpoint without an auth dependency

```yaml
rules:
  - id: medscribe-auth-missing
    languages: [python]
    severity: ERROR
    message: >
      FastAPI route under /api/v1/{notes,transcripts,audio} declared without an
      auth/ABAC dependency. Every PHI endpoint must enforce auth server-side.
    patterns:
      - pattern: |
          @$ROUTER.$METHOD("$PATH", ...)
          def $FUNC(...):
              ...
      - metavariable-regex:
          metavariable: $PATH
          regex: '/api/v1/(notes|transcripts|audio).*'
      - pattern-not: |
          @$ROUTER.$METHOD("$PATH", ..., dependencies=[Depends(require_auth)])
          def $FUNC(...):
              ...
```

## 2. `phi-in-logs` — PHI variable names in log calls (T-006)

```yaml
rules:
  - id: medscribe-phi-in-logs
    languages: [python]
    severity: ERROR
    message: >
      Possible PHI written to logs. Do not log transcript/note/patient content.
      Log identifiers as hashed values only.
    patterns:
      - pattern-either:
          - pattern: logger.$LEVEL(..., $X, ...)
          - pattern: logging.$LEVEL(..., $X, ...)
      - metavariable-regex:
          metavariable: $X
          regex: '.*(transcript|patient_name|dob|mrn|ssn|note_content|phi).*'
```

## 3. `llm-output-handling` — unvalidated LLM output (T-007 / T-014)

```yaml
rules:
  - id: medscribe-llm-output-handling
    languages: [python]
    severity: WARNING
    message: >
      Vertex AI response used without passing through the Output Validation
      Service. LLM output is untrusted: validate schema + scan for PHI before use.
    patterns:
      - pattern: |
          $RESP = vertex_client.generate_content(...)
          ...
      - pattern-not-inside: |
          $RESP = vertex_client.generate_content(...)
          ...
          output_validation.validate($RESP, ...)
          ...
```
