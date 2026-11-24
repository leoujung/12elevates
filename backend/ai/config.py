"""Single source of truth for AI matching feature flags.

Decision "Opsi 1 - Remove Environment Variable Activation" (directive 12E-DIR-ADP-001):
  - BUSINESS_MATCHING_ENABLED is a permanent False constant in this file.
  - No environment variable, runtime override, fallback, or alternate mechanism can enable it.
  - Enabling Business Matching requires a code change that references a written decision of
    the Data Controller under valid management authority, is reviewed and approved, has an
    audit trail and automated tests, and satisfies lawful basis, Privacy Notice, data
    classification and DPIA before any production processing.
  - Customer Matching is governed by its own controls and is not affected here.
"""
from __future__ import annotations

# Decision "Opsi 1 — Remove Environment Variable Activation":
# no environment variable, runtime override, or fallback can enable Business Matching.
BUSINESS_MATCHING_ENABLED: bool = False
