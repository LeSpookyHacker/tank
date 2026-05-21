# Reference — example leaked-credential patterns

> **Why this file exists**: it's a deliberate test bed for Tank's
> `secret_token` redaction rule. The strings below should all be
> caught by detect-secrets plugins or the entropy fallback, hashed
> one-way in the redaction map, and **NEVER** sent to Claude in
> cleartext. None of these are real credentials — they're the
> AWS-published documentation example, an obvious-fake Slack token,
> and an obvious-fake GitHub PAT.

## AWS access key

```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

The `AKIAIOSFODNN7EXAMPLE` value is the AWS-published example access
key ID; the matching secret is also the published example. Both
are intentionally non-functional.

## Slack bot token

```
SLACK_BOT_TOKEN=xoxb-1234567890-ABCDEFGHIJ
```

## GitHub personal access token (classic)

```
GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz
```

## Generic high-entropy string (should be caught by entropy fallback)

```
SECRET_VALUE=Z9aQpL2vR5tY8wXcM3nK7jH1bF6dG4sP0eU3iO9rT2yN5xV8
```

## Realistic-looking JWT

```
EXAMPLE_JWT=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0Iiwic2NvcGUiOiJ0ZXN0In0.x4VbW_Z6cTbq_n8YQqXmPaKv0bRzZb6BqJj_NaP3K6w
```

## What Tank should do with this file on ingest

1. Detect each of the above as `secret_token`.
2. Replace each with `[SECRET_<n>]`.
3. In `redaction_map`, store the SHA-256 hash of each original — NOT
   the cleartext — in the `original_text` column.
4. Verify by running:

   ```sql
   SELECT placeholder, original_text
     FROM redaction_map
     WHERE category = 'secret_token';
   ```

   Every `original_text` value should be a 64-character hex string
   (a SHA-256 hash), not any of the strings above in cleartext.

## What Tank should NOT do

- Should NOT include any of these strings in any outbound API call.
- Should NOT rehydrate `[SECRET_<n>]` back to cleartext in chat or
  report output. The user must look up the original in this file
  themselves if they need it.
