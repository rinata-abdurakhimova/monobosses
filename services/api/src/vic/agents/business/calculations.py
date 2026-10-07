"""Explicit, reproducible market scenarios. No numbers are inferred by an LLM."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketScenario(BaseModel):
    """Caller-reviewed inputs: annual price per patient, not company revenue."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: Literal["downside", "base", "upside"]
    population: Decimal | None = Field(default=None, ge=0)
    eligible_fraction: Decimal | None = Field(default=None, ge=0, le=1)
    access_fraction: Decimal | None = Field(default=None, ge=0, le=1)
    annual_price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    geography: str = Field(min_length=1)
    as_of_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    assumptions: list[str] = Field(min_length=1)
    # Every populated numeric input must reference supplied evidence.
    input_evidence_ids: dict[str, list[str]]


def estimate_market_scenarios(scenarios: list[MarketScenario]) -> list[dict]:
    """Calculate annual market opportunity; missing differs from a known zero.

    population × eligibility × access × annual price. This is a scenario,
    not predicted revenue or return. Decimal strings preserve exact arithmetic.
    """
    if len({s.name for s in scenarios}) != len(scenarios):
        raise ValueError("Scenario names must be unique")
    results = []
    for s in scenarios:
        missing = [k for k in ("population", "eligible_fraction", "access_fraction", "annual_price")
                   if getattr(s, k) is None]
        eligible = (s.population * s.eligible_fraction
                    if s.population is not None and s.eligible_fraction is not None else None)
        patients = (s.population * s.eligible_fraction * s.access_fraction
                    if not any(k in missing for k in ("population", "eligible_fraction", "access_fraction"))
                    else None)
        opportunity = patients * s.annual_price if not missing else None
        results.append({
            "inputs": s.model_dump(mode="json"), "missing_inputs": missing,
            "eligible_patients": str(eligible) if eligible is not None else None,
            "addressable_patients": str(patients) if patients is not None else None,
            "annual_market_opportunity": str(opportunity) if opportunity is not None else None,
            "formula": "population * eligible_fraction * access_fraction * annual_price",
            "limitation": "Scenario opportunity, not company revenue or investment return.",
        })
    return results


def summarize_market_ranges(results: list[dict]) -> list[dict]:
    """Observed scenario bounds within a comparable currency/region/date only.

    These are not confidence intervals, forecasts, or sums across regions.
    Missing opportunities are excluded; zero remains a valid bound.
    """
    groups = {}
    for result in results:
        if result["annual_market_opportunity"] is None:
            continue
        inputs = result["inputs"]
        key = (inputs["currency"], inputs["geography"], inputs["as_of_date"])
        groups.setdefault(key, []).append(result)
    return [{"currency": key[0], "geography": key[1], "as_of_date": key[2],
             "scenario_names": [r["inputs"]["name"] for r in rows],
             "minimum": str(min(Decimal(r["annual_market_opportunity"]) for r in rows)),
             "maximum": str(max(Decimal(r["annual_market_opportunity"]) for r in rows)),
             "limitation": "Bounds of supplied complete scenarios only; not a confidence interval."
             } for key, rows in groups.items()]
