# STA Rule Registry v0.1 and Escalation Policy v0.1

## Purpose
This package completes the v0.1 architectural loop by:
- Separating the rule set from the constraint engine core (Rule Registry)
- Formalizing deterministic escalation logic (Escalation Policy)

## Rule Registry (v0.1)
- Maps `signal_id` → `rule_id`
- Defines deterministic conditions on envelope fields
- Declares violation type and minimum escalation floor per rule

## Escalation Policy (v0.1)
Deterministic mapping from:
- `structural_risk_score`
- number of violations

to:
- `none | advisory | board_review | critical`

Rule-specific `escalation_level_min` acts as a floor.

## Compatibility
Additive-only within the same MAJOR version.
No key renames; deprecate instead.