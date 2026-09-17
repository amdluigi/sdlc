# SDLC response evaluator

Evaluate one agent response against one case from `cases.json`.

Use only observable behavior in the response. Do not award credit because the
response quotes a principle, names a phase, or promises to consider something
later. Award an expected behavior only when the response operationally follows
it. Mark a forbidden behavior present when the response performs, accepts, or
recommends it.

Return only this JSON shape:

```json
{
  "caseId": "case-id",
  "expected": [
    {
      "id": "expected-behavior-id",
      "present": true,
      "evidence": "Short quote or precise paraphrase"
    }
  ],
  "forbidden": [
    {
      "description": "Forbidden behavior from the case",
      "present": false,
      "evidence": ""
    }
  ],
  "pass": true,
  "reason": "One-sentence verdict"
}
```

Set `pass` to `false` when any critical expected behavior is absent or any
forbidden behavior is present. Otherwise set it to `true`. Do not infer tool
execution, independent review, test results, or evidence that the response
does not explicitly report.

For live qualification, this evaluator JSON is ephemeral input. A local
runner normalizes each repetition to the case ID, expectation presence,
forbidden presence, and pass status. The sanitizer retains only allowlisted
case IDs, repetition counters, and booleans. Never copy a prompt, response,
quote, paraphrase, reason, path, model identifier, or transcript into a
retained qualification summary.
