"""Reviewed investment inputs and deterministic arithmetic, independent of LLM output."""
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
ScenarioName = Literal["downside", "base", "upside"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ReviewedRange(StrictInput):
    """Both bounds known or both null; zero is a known value. No inferred estimates."""
    minimum: Decimal | None = Field(ge=0)
    maximum: Decimal | None = Field(ge=0)
    evidence_ids: list[Text]
    assumptions: list[Text]
    unknowns: list[Text]

    @model_validator(mode="after")
    def coherent(self):
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("Provide both bounds or neither")
        if self.minimum is None:
            if not self.unknowns:
                raise ValueError("Missing range requires explicit unknowns")
        elif self.minimum > self.maximum or not self.evidence_ids:
            raise ValueError("Known range requires ordered bounds and evidence IDs")
        return self


class CostItem(StrictInput):
    id: Identifier
    category: Literal["research", "clinical", "cro", "cmc", "regulatory", "ip",
                      "operations", "contingency", "other"]
    description: Text
    scope: Literal["development", "diligence"]
    work_ids: list[Identifier]
    amount: ReviewedRange
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    scale: Literal["units", "thousand", "million"]


class ScheduleTask(StrictInput):
    work_id: Identifier
    duration_days: ReviewedRange
    depends_on: list[Identifier]


class InvestmentScenario(StrictInput):
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
    # Restricted funds allocated to THIS asset and horizon, not company-wide cash.
    allocated_asset_cash: ReviewedRange

    @model_validator(mode="after")
    def coherent(self):
        if len({c.id for c in self.costs}) != len(self.costs):
            raise ValueError("Duplicate cost IDs")
        if len({t.work_id for t in self.schedule}) != len(self.schedule):
            raise ValueError("Duplicate schedule work IDs")
        if any(c.currency != self.currency for c in self.costs):
            raise ValueError("Mixed currencies require explicit external conversion before input")
        if self.cost_coverage != "full" and not self.cost_unknowns:
            raise ValueError("Incomplete cost coverage requires gaps")
        if self.schedule_coverage != "full" and not self.schedule_unknowns:
            raise ValueError("Incomplete schedule coverage requires gaps")
        if self.cost_coverage == "full" and (self.cost_unknowns or not any(
                c.scope == "development" for c in self.costs) or any(
                c.amount.minimum is None for c in self.costs if c.scope == "development")):
            raise ValueError("Full cost coverage requires complete development costs")
        if self.schedule_coverage == "full" and (self.schedule_unknowns or not self.schedule or any(
                t.duration_days.minimum is None for t in self.schedule)):
            raise ValueError("Full schedule requires complete durations")
        _schedule_bounds(self.schedule)  # Reject dangling edges/cycles even for partial plans.
        return self


class StressScenario(StrictInput):
    id: Identifier
    base_scenario_id: Identifier
    kind: Literal["delay", "additional_studies", "weaker_results"]
    assumptions: list[Text] = Field(min_length=1)
    # Incremental elapsed time after accounting for overlap, supplied by reviewer.
    incremental_delay_days: ReviewedRange
    incremental_cost: ReviewedRange
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    cost_scale: Literal["units", "thousand", "million"]
    burn_per_day: ReviewedRange
    cost_coverage: Literal["full", "partial", "unknown"]
    unknowns: list[Text]

    @model_validator(mode="after")
    def coherent(self):
        if self.cost_coverage != "full" and not self.unknowns:
            raise ValueError("Incomplete stress coverage requires gaps")
        if self.cost_coverage == "full" and (self.unknowns or any(r.minimum is None for r in (
                self.incremental_delay_days, self.incremental_cost, self.burn_per_day))):
            raise ValueError("Full stress coverage requires all incremental inputs")
        return self


def _schedule_bounds(tasks):
    by_id = {t.work_id: t for t in tasks}
    done, visiting = {}, set()

    def finish(work_id):
        if work_id not in by_id:
            raise ValueError("Unknown schedule dependency")
        if work_id in visiting:
            raise ValueError("Cyclic schedule dependencies")
        if work_id in done:
            return done[work_id]
        visiting.add(work_id)
        task = by_id[work_id]
        if work_id in task.depends_on or len(set(task.depends_on)) != len(task.depends_on):
            raise ValueError("Invalid schedule dependency")
        predecessors = [finish(p) for p in task.depends_on]
        duration = task.duration_days
        if duration.minimum is None or any(p is None for p in predecessors):
            result = None
        else:
            result = (max((p[0] for p in predecessors), default=Decimal(0)) + duration.minimum,
                      max((p[1] for p in predecessors), default=Decimal(0)) + duration.maximum)
        visiting.remove(work_id)
        done[work_id] = result
        return result

    for work_id in by_id:
        finish(work_id)
    if not done or any(v is None for v in done.values()):
        return None
    return max(v[0] for v in done.values()), max(v[1] for v in done.values())


def _precision(values):
    # Enough significant digits for sums/products of every finite supplied Decimal.
    return max(50, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent)
                       for v in values if v is not None) + 20)


def _decimals(value):
    if isinstance(value, Decimal):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _decimals(getattr(value, name))
    elif isinstance(value, list):
        for child in value:
            yield from _decimals(child)


def _bounds(pair):
    return {"minimum": str(pair[0]), "maximum": str(pair[1])} if pair else None


def _money(item):
    multiplier = {"units": Decimal(1), "thousand": Decimal(1000), "million": Decimal(1000000)}[item.scale]
    return (item.amount.minimum * multiplier, item.amount.maximum * multiplier)


def calculate_investment_scenarios(scenarios: list[InvestmentScenario],
                                   stresses: list[StressScenario] | None = None) -> dict:
    """No FX, probabilities, valuation, returns or funding inferred from market size.

    Schedule = longest dependency path, not sum of parallel tasks. Bounds are
    input-scenario envelopes, never confidence intervals or approval forecasts.
    """
    stresses = stresses or []
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Duplicate scenario IDs")
    keys = [(s.milestone_id, s.horizon, s.name, s.currency, s.geography, s.as_of_date)
            for s in scenarios]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate scenario in comparable group")
    if len({s.id for s in stresses}) != len(stresses):
        raise ValueError("Duplicate stress IDs")
    by_id = {s.id: s for s in scenarios}
    if any(s.base_scenario_id not in by_id for s in stresses):
        raise ValueError("Unknown stress base scenario")
    rows, stress_rows = [], []
    with localcontext() as arithmetic:
        arithmetic.prec = _precision(list(_decimals(scenarios)) + list(_decimals(stresses)))
        for s in scenarios:
            subtotals = {}
            for scope in ("development", "diligence"):
                items = [c for c in s.costs if c.scope == scope and c.amount.minimum is not None]
                subtotals[scope] = (sum((_money(c)[0] for c in items), Decimal(0)),
                                    sum((_money(c)[1] for c in items), Decimal(0))) if items else None
            capital = subtotals["development"] if s.cost_coverage == "full" else None
            elapsed = _schedule_bounds(s.schedule) if s.schedule_coverage == "full" else None
            cash = s.allocated_asset_cash
            gap = (max(capital[0] - cash.maximum, Decimal(0)),
                   max(capital[1] - cash.minimum, Decimal(0))) if capital and cash.minimum is not None else None
            rows.append({"id": s.id, "inputs": s.model_dump(mode="json"),
                "normalized_costs": [{"id": c.id, "scope": c.scope, "currency": s.currency,
                    "amount_in_currency_units": _bounds(_money(c)) if c.amount.minimum is not None else None}
                    for c in s.costs],
                "known_development_subtotal": _bounds(subtotals["development"]),
                "known_diligence_subtotal": _bounds(subtotals["diligence"]),
                "capital_to_milestone": _bounds(capital), "time_to_milestone_days": _bounds(elapsed),
                "funding_gap": _bounds(gap),
                "formula": {"capital": "sum(development cost bounds * scale); diligence excluded",
                    "time": "max(finish(task)); finish = max(finish(predecessors)) + duration_days",
                    "funding_gap": "[max(capital.min - allocated_cash.max, 0), max(capital.max - allocated_cash.min, 0)]"},
                "limitation": "Reviewed coverage declaration, not semantic verification. Bounds of supplied assumptions; no return forecast."})
        calculated = {r["id"]: r for r in rows}
        for stress in stresses:
            base = by_id[stress.base_scenario_id]
            if stress.currency != base.currency:
                raise ValueError("Stress currency differs from base")
            scale = {"units": Decimal(1), "thousand": Decimal(1000), "million": Decimal(1000000)}[stress.cost_scale]
            delay, extra, burn = stress.incremental_delay_days, stress.incremental_cost, stress.burn_per_day
            incremental = None
            if stress.cost_coverage == "full":
                incremental = (extra.minimum * scale + delay.minimum * burn.minimum,
                               extra.maximum * scale + delay.maximum * burn.maximum)
            row = calculated[base.id]
            capital, time = row["capital_to_milestone"], row["time_to_milestone_days"]
            stressed_capital = (Decimal(capital["minimum"]) + incremental[0],
                               Decimal(capital["maximum"]) + incremental[1]) if capital and incremental else None
            stressed_time = (Decimal(time["minimum"]) + delay.minimum,
                             Decimal(time["maximum"]) + delay.maximum) if time and delay.minimum is not None else None
            cash = base.allocated_asset_cash
            gap = (max(stressed_capital[0] - cash.maximum, Decimal(0)),
                   max(stressed_capital[1] - cash.minimum, Decimal(0))) if stressed_capital and cash.minimum is not None else None
            stress_rows.append({"id": stress.id, "inputs": stress.model_dump(mode="json"),
                "incremental_budget": _bounds(incremental), "stressed_capital": _bounds(stressed_capital),
                "stressed_time_days": _bounds(stressed_time), "stressed_funding_gap": _bounds(gap),
                "formula": "extra_cost * scale + incremental_delay_days * burn_per_day (currency units/day)",
                "limitation": "No double counting permitted in reviewed inputs; excludes valuation, financing terms and success probability."})
    groups = {}
    for row in rows:
        s = by_id[row["id"]]
        key = (s.milestone_id, s.horizon, s.currency, s.geography, s.as_of_date.isoformat())
        groups.setdefault(key, []).append(row)
    ranges = []
    for key, group in groups.items():
        bounds = {}
        for metric in ("capital_to_milestone", "time_to_milestone_days", "funding_gap"):
            complete = [r for r in group if r[metric] is not None]
            bounds[metric] = _bounds((min(Decimal(r[metric]["minimum"]) for r in complete),
                                     max(Decimal(r[metric]["maximum"]) for r in complete))) if complete else None
            bounds[metric + "_scenario_ids"] = [r["id"] for r in complete]
        ranges.append({"milestone_id": key[0], "horizon": key[1], "currency": key[2],
            "geography": key[3], "as_of_date": key[4], **bounds,
            "limitation": "Bounds of complete supplied scenarios only; missing scenarios excluded; no confidence interval."})
    return {"scenarios": rows, "scenario_ranges": ranges, "stress_scenarios": stress_rows}
