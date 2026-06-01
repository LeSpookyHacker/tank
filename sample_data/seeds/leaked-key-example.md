# Secret-Leak Examples (redaction test fixtures)

> These are **fake** credentials planted to prove Tank's redaction engine
> catches secrets before anything is sent to Claude. Every value below must be
> replaced by a `[SECRET_xxx]` placeholder in the redacted view.

During the first-week review the new AppSec hire found these examples of secrets
that had leaked into a config dump and a public gist. Treat as illustrative only.

## Cloud / vendor keys

- AWS access key id: `AKIAIOSFODNN7EXAMPLE`
- aws_secret_access_key = `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
- Vertex AI / Google API key: `AIzaSyDmedscribeFAKEvertexkey0123456789`
- Slack bot token (alerts webhook): `xoxb-7700000000-MedScribeFAKEtoken00`
- GitHub PAT (CI mirror): `ghp_abcdefghijklmnopqrstuvwxyz0123456789`

## A JWT that was pasted into a ticket

`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjbGluaWNpYW4iLCJ0ZW5hbnQiOiJ0LTAwMSJ9.3hT2kPq9sVnWmAhTnDfR4sYbNZk9xQ2pL7vWcXyZabc`

## A GCP service-account private key (found in an old branch)

```
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDFAKEmedscribe
b1Qn3xampleKeyMaterialNotRealb2Qn3xampleKeyMaterialNotRealc3Qn3xa
mpleKeyMaterialNotReald4Qn3xampleKeyMaterialNotReale5Qn3xampleKey
-----END PRIVATE KEY-----
```

If any of the values above survive into a `*_redacted` column, the redaction
engine has failed — stop using Tank for real data until it is fixed.
