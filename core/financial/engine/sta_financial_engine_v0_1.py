#!/usr/bin/env python3
# STA Financial Engine v0.1
# Reads: STA_Pilot_Financials_v0_1.json (root)
# Reads: core/financial/constraints/STA_Financial_Constraint_Pack_v0_1.json
# Reads: core/financial/rules/STA_Financial_Rule_Pack_v0_1.json
# Writes: core/financial/output/STA_Financial_Run_Report_v0_1.json + .md

from __future__ import annotations
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


ROOT_INPUT_DEFAULT = "STA_Pilot_Financials_v0_1.json"
CONSTRAINTS_DEFAULT = "core/financial/constraints/STA_Financial_Constraint_Pack_v0_1.json"
RULES_DEFAULT = "core/financial/rules/STA_Financial_Rule_Pack_v0_1.json"
OUTPUT_JSON_DEFAULT = "core/financial/output/STA_Financial_Run_Report_v0_1.json"
OUTPUT_MD_DEFAULT = "core/financial/output/STA_Financial_Run_Report_v0_1.md"


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        if math.isnan(x):
            return None
        return float(x)
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        # allow "1 234" and "1,234"
        s = s.replace(" ", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _abs_tol_pass(delta: float, abs_tol: float, pct_tol: float, base: float) -> bool:
    # Pass if within absolute tolerance OR within percentage tolerance.
    if abs(delta) <= abs_tol:
        return True
    if base == 0:
        return False
    return abs(delta) <= abs(base) * pct_tol


@dataclass
class Signal:
    type: str
    severity: str
    entity_id: str
    statement: str
    message: str
    details: Dict[str, Any]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _parse_dataset(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Returns:
      entities[entity_id]["BS"][line_id] = {"closing":..., "opening":..., "delta":...}
      entities[entity_id]["IS"][line_id] = {"amount":...}
      entities[entity_id]["EQ"][line_id] = {"amount":...}
    Dataset structure is your exported JSON with sheets: BS, IS, EQ.
    """
    sheets = dataset.get("sheets", {})
    entities: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # --- BS ---
    bs_rows = sheets.get("BS", [])
    # Row 0/1 are headers in your file; data rows have entity in col 0 and line_id in col 1
    for r in bs_rows:
        entity = str(r.get("Balance_sheet", "")).strip()
        line_id = str(r.get("Unnamed: 1", "")).strip()
        closing = _to_float(r.get("Unnamed: 2"))
        opening = _to_float(r.get("Unnamed: 3"))
        delta = _to_float(r.get("Unnamed: 4"))

        if entity == "" or line_id == "":
            continue

        entities.setdefault(entity, {}).setdefault("BS", {})
        entities[entity]["BS"][line_id] = {
            "closing": closing,
            "opening": opening,
            "delta": delta,
        }

    # --- IS ---
    is_rows = sheets.get("IS", [])
    for r in is_rows:
        entity = str(r.get("Income statement", "")).strip()
        line_id = str(r.get("Unnamed: 1", "")).strip()
        amount = _to_float(r.get("Unnamed: 2"))

        if entity == "" or line_id == "":
            continue

        entities.setdefault(entity, {}).setdefault("IS", {})
        entities[entity]["IS"][line_id] = {"amount": amount}

    # --- EQ ---
    eq_rows = sheets.get("EQ", [])
    for r in eq_rows:
        entity = str(r.get("Equity", "")).strip()
        line_id = str(r.get("Unnamed: 1", "")).strip()
        amount = _to_float(r.get("Unnamed: 2"))

        if entity == "" or line_id == "":
            continue

        entities.setdefault(entity, {}).setdefault("EQ", {})
        entities[entity]["EQ"][line_id] = {"amount": amount}

    return entities


def _rule_lookup(rules_pack: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in rules_pack.get("rules", []):
        st = r.get("signal_type")
        if st:
            out[st] = r
    return out


def _severity_default(signal_type: str) -> str:
    # fallback if no rule exists
    if signal_type.startswith("FIN.") and "CRITICAL" in signal_type:
        return "CRITICAL"
    return "MEDIUM"


def _apply_rules(signal: Signal, rule_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    r = rule_map.get(signal.type, {})
    return {
        "risk_level": r.get("risk_level", "UNSPECIFIED"),
        "escalation": r.get("escalation", "UNSPECIFIED"),
        "rule_id": r.get("rule_id", "UNSPECIFIED"),
    }


def run(
    dataset_path: str = ROOT_INPUT_DEFAULT,
    constraints_path: str = CONSTRAINTS_DEFAULT,
    rules_path: str = RULES_DEFAULT,
    out_json: str = OUTPUT_JSON_DEFAULT,
    out_md: str = OUTPUT_MD_DEFAULT,
) -> Tuple[str, str]:
    dataset = _load_json(dataset_path)
    constraints_pack = _load_json(constraints_path)
    rules_pack = _load_json(rules_path)
    rule_map = _rule_lookup(rules_pack)

    entities = _parse_dataset(dataset)

    abs_default = float(constraints_pack.get("tolerance_defaults", {}).get("absolute", 1000))
    pct_default = float(constraints_pack.get("tolerance_defaults", {}).get("percentage", 0.001))

    signals: List[Signal] = []

    for entity_id, stmts in entities.items():
        bs = stmts.get("BS", {})
        is_ = stmts.get("IS", {})
        eq = stmts.get("EQ", {})

        # ---------- Constraint: BS equation ----------
        # Your BS has AssetsTotal and LiabilitiesAndEquityTotal (often the same total).
        # If the pack expects EquityTotal + LiabilitiesTotal but LiabilitiesTotal is missing,
        # we derive LiabilitiesTotal = LiabilitiesAndEquityTotal - EquityTotal.
        assets = _to_float(bs.get("AssetsTotal", {}).get("closing"))
        le_total = _to_float(bs.get("LiabilitiesAndEquityTotal", {}).get("closing"))
        equity_total = _to_float(bs.get("EquityTotal", {}).get("closing"))

        abs_tol = abs_default
        pct_tol = pct_default

        if assets is not None and le_total is not None:
            delta = assets - le_total
            base = le_total
            if not _abs_tol_pass(delta, abs_tol, pct_tol, base):
                signals.append(
                    Signal(
                        type="FIN.BS.EQUATION_BREAK",
                        severity="CRITICAL",
                        entity_id=entity_id,
                        statement="BS",
                        message="Balance sheet equation fails: AssetsTotal != LiabilitiesAndEquityTotal beyond tolerance.",
                        details={
                            "AssetsTotal": assets,
                            "LiabilitiesAndEquityTotal": le_total,
                            "delta": delta,
                            "tolerance_abs": abs_tol,
                            "tolerance_pct": pct_tol,
                        },
                    )
                )

        # ---------- Constraint: EQ roll-forward ----------
        opening = _to_float(eq.get("EquityOpening", {}).get("amount"))
        closing = _to_float(eq.get("EquityClosing", {}).get("amount"))

        # accept either ProfitAfterTax or ProfitForTheYear
        profit = _to_float(eq.get("ProfitForTheYear", {}).get("amount"))
        if profit is None:
            profit = _to_float(eq.get("ProfitAfterTax", {}).get("amount"))

        # accept DividendsPaid or Dividends
        dividends = _to_float(eq.get("Dividends", {}).get("amount"))
        if dividends is None:
            dividends = _to_float(eq.get("DividendsPaid", {}).get("amount"))

        other = _to_float(eq.get("OtherEquityMovements", {}).get("amount"))
        if other is None:
            other = 0.0

        if opening is not None and closing is not None:
            # missing profit/dividends treated as 0
            p = profit if profit is not None else 0.0
            d = dividends if dividends is not None else 0.0
            expected = opening + p - d + other
            delta = expected - closing
            base = closing
            if not _abs_tol_pass(delta, abs_tol, pct_tol, base):
                signals.append(
                    Signal(
                        type="FIN.EQ.ROLLFORWARD_BREAK",
                        severity="CRITICAL",
                        entity_id=entity_id,
                        statement="EQ",
                        message="Equity roll-forward fails beyond tolerance.",
                        details={
                            "EquityOpening": opening,
                            "Profit": p,
                            "Dividends": d,
                            "OtherEquityMovements": other,
                            "ExpectedEquityClosing": expected,
                            "EquityClosing": closing,
                            "delta": delta,
                            "tolerance_abs": abs_tol,
                            "tolerance_pct": pct_tol,
                        },
                    )
                )

        # ---------- Constraint: Dividend plausibility (pilot) ----------
        # Simple structural test: abs(DividendsPaid) should not exceed abs(EquityClosing) by much.
        if closing is not None and dividends is not None:
            if abs(dividends) > abs(closing) + abs_tol:
                signals.append(
                    Signal(
                        type="FIN.DIV.LEGALITY_IMPOSSIBLE",
                        severity="CRITICAL",
                        entity_id=entity_id,
                        statement="EQ",
                        message="Dividend appears structurally impossible relative to closing equity capacity (pilot test).",
                        details={
                            "Dividends": dividends,
                            "EquityClosing": closing,
                            "threshold": abs(closing) + abs_tol,
                            "tolerance_abs": abs_tol,
                        },
                    )
                )

        # ---------- Heuristic: large income without matching receivable movement (optional) ----------
        extraordinary_income = _to_float(is_.get("ExtraordinaryIncome", {}).get("amount"))
        recv_move = _to_float(bs.get("ReceivablesMovement", {}).get("delta"))
        if extraordinary_income is not None and recv_move is not None:
            if abs(extraordinary_income) > 1_000_000 and abs(recv_move) < abs(extraordinary_income) * 0.1:
                signals.append(
                    Signal(
                        type="FIN.DEBIT_CREDIT.MISSING_COUNTERPART",
                        severity="CRITICAL",
                        entity_id=entity_id,
                        statement="IS/BS",
                        message="Large income event without corresponding receivable movement (heuristic).",
                        details={
                            "ExtraordinaryIncome": extraordinary_income,
                            "ReceivablesMovement": recv_move,
                        },
                    )
                )

        # ---------- Heuristic: impairment large ----------
        impairment = _to_float(is_.get("Impairment_Investments", {}).get("amount"))
        if impairment is None:
            impairment = _to_float(is_.get("WriteDownsInvestments", {}).get("amount"))
        if impairment is not None and abs(impairment) >= 1_000_000:
            signals.append(
                Signal(
                    type="FIN.WRITEDOWN.CAUSALITY_BREAK",
                    severity="HIGH",
                    entity_id=entity_id,
                    statement="IS/BS",
                    message="Large impairment/write-down triggers structural review.",
                    details={
                        "Impairment": impairment,
                    },
                )
            )

    # Apply rule mappings (risk/escalation)
    out_signals: List[Dict[str, Any]] = []
    for s in signals:
        rule_applied = _apply_rules(s, rule_map)
        out_signals.append(
            {
                "type": s.type,
                "severity": s.severity,
                "entity_id": s.entity_id,
                "statement": s.statement,
                "message": s.message,
                "details": s.details,
                "risk_level": rule_applied["risk_level"],
                "escalation": rule_applied["escalation"],
                "rule_id": rule_applied["rule_id"],
            }
        )

    report = {
        "report_id": "sta.financial.run_report.v0_1",
        "input_dataset": dataset.get("source_file", ROOT_INPUT_DEFAULT),
        "signals_count": len(out_signals),
        "signals": out_signals,
    }

    _ensure_dir(out_json)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Markdown summary
    _ensure_dir(out_md)
    lines: List[str] = []
    lines.append("# STA Financial Run Report v0.1")
    lines.append("")
    lines.append(f"- Input: `{report['input_dataset']}`")
    lines.append(f"- Signals: **{report['signals_count']}**")
    lines.append("")
    if out_signals:
        lines.append("## Signals")
        lines.append("")
        for i, s in enumerate(out_signals, 1):
            lines.append(f"### {i}. {s['type']} — {s['risk_level']} — {s['escalation']}")
            lines.append(f"- Entity: `{s['entity_id']}`")
            lines.append(f"- Statement: `{s['statement']}`")
            lines.append(f"- Message: {s['message']}")
            lines.append(f"- Details: `{json.dumps(s['details'], ensure_ascii=False)}`")
            lines.append("")
    else:
        lines.append("## Signals")
        lines.append("")
        lines.append("No signals triggered.")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return out_json, out_md


if __name__ == "__main__":
    out_json, out_md = run()
    print(out_json)
    print(out_md)
