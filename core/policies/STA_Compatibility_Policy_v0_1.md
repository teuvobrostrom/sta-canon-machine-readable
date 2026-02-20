# STA Compatibility Policy v0.1

**Document:** STA_Compatibility_Policy_v0_1  
**Applies to:** STA Signal Envelope and all Signal Definitions  
**Created:** 2026-02-18T21:42:41Z  

---

## 1. Versioning Strategy

STA follows a semantic versioning-inspired structure:

- MAJOR version: Breaking structural changes
- MINOR version: Backward-compatible feature additions
- PATCH version: Non-structural corrections (documentation, constraints clarification)

Example:
- 0.1.0 → Initial draft release
- 0.2.0 → Additive schema fields
- 1.0.0 → First stability-locked release

---

## 2. Backward Compatibility Rules

### 2.1 Additive-Only Within Same Major Version

Within the same MAJOR version:
- New fields may be added
- Existing fields must NOT be removed
- Existing fields must NOT be renamed
- Existing field types must NOT change

---

### 2.2 Field Deprecation Policy

If a field must be phased out:

1. Mark it as `"deprecated": true` in schema documentation
2. Keep it functional for at least one full MINOR cycle
3. Remove only during next MAJOR version bump

---

### 2.3 Stable Identifiers

The following fields are immutable once introduced:

- `sta_version`
- `signal_id`
- `signal_category`
- `signal_type`
- `envelope_id`

These must never be repurposed or renamed.

---

## 3. Schema vs Payload Separation

- Envelope Schema defines structural container.
- Signal Definitions define payload logic.
- Envelope must remain generic and signal-agnostic.
- Signals must map to Envelope via explicit mapping section.

---

## 4. Required vs Optional Fields

Each Signal Definition must clearly declare:

- `required_fields`
- `optional_fields`

Envelope-level required fields are locked from removal in same MAJOR version.

---

## 5. Extension Rules

All future extensions must:

- Be backward compatible within same MAJOR version
- Avoid nested structural complexity unless justified
- Preserve machine-readability and deterministic evaluation

---

## 6. Major Version Transition Rule

A MAJOR version change is required if:

- A field is removed
- A field type changes
- Envelope structure is altered
- Evaluation semantics fundamentally change

---

## 7. Stability Goal

Objective:

Reach STA v1.0 with:

- Frozen Envelope core
- At least 3 stable signal definitions
- Defined evaluation engine interface
- Backward compatibility guaranteed for enterprise adoption

---

End of document.