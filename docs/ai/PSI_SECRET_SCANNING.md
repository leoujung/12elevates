# PSI Secret Scanning — Local Policy (PSI P0 Phase 1)

Scope: local engineering only. No CI workflow is defined here (CI host not decided, per 12E-PSI-P0-EXEC-001 item 7).
Tooling: gitleaks v8.30.1 (windows_x64). Binary SHA-256 verified against the upstream checksums file before use.

## What is enforced locally

1. **pre-commit hook** (`.pre-commit-config.yaml`): runs `gitleaks protect --staged` on every commit. A commit containing a detected secret is rejected.
2. **Config** (`.gitleaks.toml`): default gitleaks rules (`useDefault = true`). No custom rules and no global allowlist.
3. **Fail-closed:** if `GITLEAKS_BIN` is not set, the hook refuses every commit with an explicit message. It never silently passes.

## Setup (per clone)

```
set GITLEAKS_BIN=C:\path\to\verified\gitleaks.exe
python -m pre_commit install
```

The binary must be obtained from the upstream release and its checksum verified against `gitleaks_<version>_checksums.txt` before use.

## Allowlist policy

- Allowlisting is **per fingerprint only**, through `.gitleaksignore`. Never by path, directory, or regex.
- Each entry must record: fingerprint, reason, owner, approver, expiry (maximum 90 days).
- **Exposed secrets are never allowlisted.** This includes the `357240c` strata key. Their finding stays OPEN until rotation or revocation is verified (12E-PSI-P0-REVISION-001, D-Exposed).
- Synthetic test keys may be allowlisted by fingerprint so the scanner does not block the suite. A real key placed in a test file must still be detected.

Current state: **no allowlist entries exist.**

## Verified behavior (local, this revision)

| Test | Input | Expected | Result |
|---|---|---|---|
| A | staged synthetic AWS-shaped key (value not reproduced here; see test fixture note) | blocked, exit 1 | exit 1, 1 leak found |
| B | staged clean file | allowed, exit 0 | exit 0 |
| D | committed synthetic key, history scan | detected, exit 1 | exit 1, 1 leak found |
| P1 | pre-commit with synthetic key staged | commit rejected, commit count unchanged | rejected, count unchanged |
| P2 | pre-commit with clean file | commit allowed | Passed |
| P0 | pre-commit with `GITLEAKS_BIN` unset | fail closed with message | fail closed |

Note on test selection: the AWS documentation example key is ignored by gitleaks default stopwords, so it cannot serve as a positive test. The test uses a synthetic key of the same shape that is not a stopword. The key value is not reproduced in documentation, to avoid the document itself being flagged.

## Known limits

- Scanning covers staged content and commit history reachable from the repository. Files git ignores cannot be committed, so they are protected by `.gitignore`, not by the scanner.
- The hook runs only where it is installed. A commit made with `--no-verify` bypasses it. CI enforcement is deferred until the CI host is decided, and is required before any scanner-clean claim.
- The hook is not a substitute for rotation. A value found in history is still compromised.

## Prevention of secret values in logs

- `backend/tests/test_psi_log_leak.py` captures all Python log records at DEBUG and stdout/stderr during the PSI operator-authorization path, and fails if a synthetic key or raw member ID appears.
- Negative control verified: a deliberate log of the key made 2 tests fail. The probe was reverted and the source restored byte-identical.

## Not covered by this policy

- Remediation of the `357240c` strata key (rotation or revocation). This is a separate, Director-owned task.
- Vault/OpenBao migration (required before real data).
- CI workflow (blocked on CI host decision).
