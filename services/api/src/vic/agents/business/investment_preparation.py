"""Source-bound numeric proposals -> Python inputs. No LLM arithmetic or executable formulas."""
from datetime import date
from decimal import Decimal, localcontext
import re
from typing import Literal

from pydantic import Field

from vic.contracts import EvidencePack
from .investment_calculations import (
    CostItem, Identifier, InvestmentScenario, ReviewedRange, ScheduleTask, ScenarioName,
    StrictInput, StressScenario, Text, _precision,
)


class ScenarioBlueprint(StrictInput):
    """Plan skeleton: numeric ranges must be null until Python resolves bindings."""
    id: Identifier
    name: ScenarioName
    milestone_id: Identifier
    horizon: Literal["next_milestone", "future_milestone"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    geography: Text
    as_of_date: date
    assumptions: list[Text] = Field(min_length=1)
    costs: list[CostItem]
    cost_coverage: Literal["full", "partial", "unknown"]
    cost_unknowns: list[Text]
    schedule: list[ScheduleTask]
    schedule_coverage: Literal["full", "partial", "unknown"]
    schedule_unknowns: list[Text]
    allocated_asset_cash: ReviewedRange


class StressBlueprint(StrictInput):
    id: Identifier
    base_scenario_id: Identifier
    trigger_id: Identifier
    kind: Literal["delay", "additional_studies", "weaker_results"]
    assumptions: list[Text] = Field(min_length=1)
    incremental_delay_days: ReviewedRange
    incremental_cost: ReviewedRange
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    cost_scale: Literal["units", "thousand", "million"]
    burn_per_day: ReviewedRange
    cost_coverage: Literal["full", "partial", "unknown"]
    unknowns: list[Text]


class NumericOperand(StrictInput):
    """Verbatim number tokens and unit from one supplied excerpt, not model estimates."""
    evidence_id: Text
    quote: Text
    minimum_text: Text
    maximum_text: Text
    unit: Literal["units", "thousand", "million", "days", "count", "units_per_item",
                  "thousand_per_item", "million_per_item", "units_per_day"]
    unit_text: Text
    currency: str | None = Field(pattern=r"^[A-Z]{3}$")


class NumericBinding(StrictInput):
    record_type: Literal["scenario", "stress"]
    record_id: Identifier
    # e.g. costs.study.amount, schedule.study.duration_days, allocated_asset_cash.
    input_path: Text
    operation: Literal["copy", "multiply"]
    operands: list[NumericOperand] = Field(min_length=1, max_length=2)
    basis: Literal["direct", "analogue"]
    applicability: Text
    assumptions: list[Text]
    unknowns: list[Text]


def _number(token: str, quote: str) -> Decimal:
    # Explicit English numeric notation only: 1,000.50 or 1000.50. No guessing locale/FX.
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", token):
        raise ValueError("Unsupported numeric notation; leave unknown instead of guessing")
    matches = list(re.finditer(r"(?<![\w.,])" + re.escape(token) + r"(?![\w.,])", quote))
    def negative_prefix(match):
        prefix = quote[:match.start()].rstrip()
        # Unicode minus and typographic/fullwidth dashes occur in copied PDFs.
        # A dash between numeric bounds (100–200) remains a range separator.
        if not prefix or prefix[-1] not in "-−﹣－‒–—":
            return False
        before_sign = prefix[:-1].rstrip()
        return not before_sign or not before_sign[-1].isdigit()

    valid = [m for m in matches if not negative_prefix(m)]
    if not valid:
        raise ValueError("Nonnegative numeric token is not present verbatim in cited quote")
    return Decimal(token.replace(",", ""))


def _operand(operand: NumericOperand, pack: EvidencePack):
    evidence = {e.id: e for e in pack.evidence}
    if operand.evidence_id not in evidence or operand.quote not in evidence[operand.evidence_id].excerpt:
        raise ValueError("Numeric quote must be an exact substring of supplied evidence")
    if operand.unit_text not in operand.quote:
        raise ValueError("Unit token must occur in numeric quote")
    low, high = _number(operand.minimum_text, operand.quote), _number(operand.maximum_text, operand.quote)
    if low > high:
        raise ValueError("Reversed cited numeric bounds")
    unit = operand.unit
    token = operand.unit_text.lower()
    if unit == "days":
        if token not in ("day", "days") or operand.currency is not None or not re.search(
                r"\b" + token + r"\b", operand.quote):
            raise ValueError("Duration operands must explicitly use days")
    elif unit == "count":
        if operand.currency is not None:
            raise ValueError("Quantity has no currency")
        if not re.fullmatch(r"(?:samples?|patients?|participants?|tests?|vials?|units?)", token) or not re.search(
                r"\b" + token + r"\b", operand.quote):
            raise ValueError("Quantity requires an explicit supported count unit")
    else:
        if operand.currency is None or not re.search(r"\b" + operand.currency + r"\b", operand.quote):
            raise ValueError("Currency must occur explicitly in cited quote")
        if unit.startswith("thousand") and "thousand" not in token:
            raise ValueError("Thousand scale must occur explicitly in unit token")
        if unit.startswith("million") and "million" not in token:
            raise ValueError("Million scale must occur explicitly in unit token")
        if unit.startswith("units") and re.search(r"\b(thousand|million)\b", operand.quote, re.I):
            raise ValueError("Currency units cannot silently ignore source scale")
        if unit.endswith("per_day") and token not in ("/day", "per day"):
            raise ValueError("Burn requires explicit daily unit")
        if unit.endswith("per_item") and not ("/" in token or "per " in token):
            raise ValueError("Unit price requires explicit per-item unit")
        if unit == "units" and operand.unit_text != operand.currency:
            raise ValueError("Unscaled money unit must identify the currency")
    factor = Decimal(1000000 if unit.startswith("million") else 1000 if unit.startswith("thousand") else 1)
    dimension = "rate" if unit.endswith("per_item") else "burn" if unit.endswith("per_day") else (
        "money" if operand.currency else unit)
    return low * factor, high * factor, dimension, operand.currency


def _targets(records):
    targets = {}
    for record_type, collection in records.items():
        for record in collection:
            if record_type == "scenario":
                for cost in record["costs"]:
                    key = (record_type, record["id"], f"costs.{cost['id']}.amount")
                    if key in targets:
                        raise ValueError("Duplicate cost input path")
                    targets[key] = (cost, "amount", "money", cost["currency"], cost["scale"])
                for task in record["schedule"]:
                    key = (record_type, record["id"], f"schedule.{task['work_id']}.duration_days")
                    if key in targets:
                        raise ValueError("Duplicate schedule input path")
                    targets[key] = (task, "duration_days", "days", None, "units")
                targets[(record_type, record["id"], "allocated_asset_cash")] = (
                    record, "allocated_asset_cash", "money", record["currency"], "units")
            else:
                for field, dimension, scale in (("incremental_delay_days", "days", "units"),
                        ("incremental_cost", "money", record["cost_scale"]),
                        ("burn_per_day", "burn", "units")):
                    targets[(record_type, record["id"], field)] = (
                        record, field, dimension, record["currency"] if dimension != "days" else None, scale)
    return targets


def resolve_numeric_inputs(blueprints: list[ScenarioBlueprint], stresses: list[StressBlueprint],
                           bindings: list[NumericBinding], pack: EvidencePack):
    """Bind only verifiable source tokens; semantic applicability still requires R3 audit.

    Missing bindings remain null. Coverage is explicit, not inferred from number presence.
    Multiply supports quantity * unit price only, with Python performing the product.
    """
    records = {"scenario": [b.model_dump(mode="json") for b in blueprints],
               "stress": [b.model_dump(mode="json", exclude={"trigger_id"}) for b in stresses]}
    for collection in records.values():
        if len({r["id"] for r in collection}) != len(collection):
            raise ValueError("Duplicate numeric blueprint IDs")
    targets = _targets(records)
    for holder, field, *_ in targets.values():
        value = holder[field]
        if value["minimum"] is not None or value["maximum"] is not None or value["evidence_ids"]:
            raise ValueError("LLM blueprint ranges must be null; use source-bound operands")
    seen, provenance = set(), []
    for binding in bindings:
        key = (binding.record_type, binding.record_id, binding.input_path)
        if key in seen or key not in targets:
            raise ValueError("Duplicate or unknown numeric binding target")
        seen.add(key)
        if binding.basis == "analogue" and not binding.assumptions:
            raise ValueError("Analogue application requires explicit assumptions")
        holder, field, dimension, currency, scale = targets[key]
        with localcontext() as ctx:
            # Parse first for precision without executing source expressions.
            values = [_number(t, o.quote) for o in binding.operands
                      for t in (o.minimum_text, o.maximum_text)]
            ctx.prec = _precision(values)
            operands = [_operand(o, pack) for o in binding.operands]
            if binding.operation == "copy":
                if len(operands) != 1:
                    raise ValueError("Copy requires one operand")
                low, high, actual_dimension, actual_currency = operands[0]
            else:
                if len(operands) != 2 or [o[2] for o in operands] != ["count", "rate"]:
                    raise ValueError("Multiply requires quantity then unit price")
                count_unit = binding.operands[0].unit_text.lower().removesuffix("s")
                price_unit = re.search(r"(?:per |/)([a-z]+)$", binding.operands[1].unit_text.lower())
                if price_unit is None or price_unit.group(1).removesuffix("s") != count_unit:
                    raise ValueError("Quantity and per-item price refer to different items")
                low, high = operands[0][0] * operands[1][0], operands[0][1] * operands[1][1]
                actual_dimension, actual_currency = "money", operands[1][3]
            if actual_dimension != dimension or actual_currency != currency:
                raise ValueError("Numeric dimension/currency differs from target")
            factor = Decimal({"units": 1, "thousand": 1000, "million": 1000000}[scale])
            holder[field] = ReviewedRange(minimum=low/factor, maximum=high/factor,
                evidence_ids=list(dict.fromkeys(o.evidence_id for o in binding.operands)),
                assumptions=binding.assumptions, unknowns=binding.unknowns).model_dump(mode="json")
        provenance.append({**binding.model_dump(mode="json"), "resolved_range": holder[field],
            "review_status": "source_tokens_checked_semantic_review_pending"})
    scenarios = [InvestmentScenario.model_validate(r) for r in records["scenario"]]
    stress_inputs = [StressScenario.model_validate(r) for r in records["stress"]]
    return scenarios, stress_inputs, provenance
