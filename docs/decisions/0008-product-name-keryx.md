# 0008 — Product name: Keryx

- **Date:** 2026-10-14
- **Status:** accepted (pending trademark and domain checks)

## Context
The project has run under the working title "Voice Agent Platform". We need a product name for the
repo, docs, dashboard and conversations with design partners.

## Decision
The product is called **Keryx**, pronounced "KERR-iks". A keryx (Greek κῆρυξ) is a herald: the one
who speaks on someone's behalf, which is what our agents do for the companies that deploy them.
The GitHub repo is `Piyush-45/Keryx`.

## Alternatives considered
- Keep "Voice Agent Platform" — descriptive, not a name; can't be trademarked or owned.

## Consequences
- Docs and repo use "Keryx". Internal package names (`vp_shared`, `vp_db`, `vp_*` DB roles) keep the
  `vp_` prefix; renaming them is churn with no user-facing value.
- **Still pending:** trademark search (India and US, classes 9/42) and domain availability. If either
  check fails, revisit this decision before any public launch or brand work.
- Spelling and pronunciation are not obvious; the pronunciation should appear wherever the name is
  introduced (site, pitch deck).
