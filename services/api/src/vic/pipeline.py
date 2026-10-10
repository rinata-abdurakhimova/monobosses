"""Pipeline: validate -> retrieve -> analyze -> audit -> synthesize -> finalize (contract section 4).

Agents never call each other: only this module does. Every expected failure becomes a typed
RunFailure and ends the run as `failed` with an explained error. A run is `completed` only
when a Report passed validation and was saved.
"""
import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from vic import integrity
from vic.config import Settings
from vic.contracts import (
    AuditResult,
    CaseInput,
    Claim,
    CommitteeDecision,
    ErrorBody,
    EvidencePack,
    Importance,
    NodeOutput,
    Recommendation,
    Report,
    RoleId,
    RoleResult,
    Run,
    RunBudget,
    RunContext,
    RunMode,
    RunStage,
    RunStatus,
    SectionContent,
    SupportStatus,
    Usage,
)
from vic.failures import ProviderAuthError, RunFailure, RunTimeout, SourceOutage, ValidationFailed
from vic.modules import STUB_ORIGIN, Modules, call_audit, call_clinical, call_investment
from vic.report_builder import build_report
from vic.storage import ReportExistsError, Repository, new_id
from vic.tracing import config_version, scrub

logger = logging.getLogger("vic")
ROLE_ORDER = [RoleId.SCIENCE, RoleId.TRANSLATION, RoleId.CLINICAL, RoleId.MARKET,
              RoleId.IP_LICENSING, RoleId.PARTNERSHIPS, RoleId.INVESTMENT,
              RoleId.INVESTMENT_THRESHOLD, RoleId.FAILURE_MINER]
_NEEDS_EVIDENCE = (SupportStatus.SUPPORTED, SupportStatus.CONTRADICTED, SupportStatus.MIXED)


def _merge(items: list, label: str) -> list:
    out: dict[str, Any] = {}
    for item in items:
        if item.id in out and out[item.id] != item:
            raise ValidationFailed(f"{label} id '{item.id}' is used by two different records",
                                   code="id_conflict")
        out.setdefault(item.id, item)
    return list(out.values())


def _expand(roles: set[RoleId]) -> set[RoleId]:
    """Roles whose input depends on a re-run role must be re-run too."""
    out = set(roles)
    dependencies = {
        RoleId.CLINICAL: {RoleId.SCIENCE, RoleId.TRANSLATION},
        RoleId.MARKET: {RoleId.CLINICAL},
        RoleId.IP_LICENSING: {RoleId.SCIENCE, RoleId.CLINICAL, RoleId.MARKET},
        RoleId.PARTNERSHIPS: {RoleId.SCIENCE, RoleId.CLINICAL, RoleId.MARKET, RoleId.IP_LICENSING},
        RoleId.INVESTMENT: {RoleId.CLINICAL, RoleId.MARKET, RoleId.IP_LICENSING, RoleId.PARTNERSHIPS},
        RoleId.INVESTMENT_THRESHOLD: set(ROLE_ORDER[:7]),
        RoleId.FAILURE_MINER: set(ROLE_ORDER[:8]),
    }
    changed = True
    while changed:
        previous = set(out)
        out.update(role for role, upstream in dependencies.items() if upstream & out)
        changed = out != previous
    return out


class Pipeline:
    def __init__(self, repo: Repository, settings: Settings, modules_factory: Callable[[], Modules],
                 llm_factory: Callable[[], Any]):
        self.repo, self.settings = repo, settings
        self._modules_factory, self._llm_factory = modules_factory, llm_factory
        self.run: Run
        self.ctx: RunContext
        self._stage: RunStage | None = None
        self._stage_started: float | None = None
        self._durations: dict[str, int] = {}
        self._report_version: int | None = None
        self._snapshot_id: str | None = None
        self._unresolved: set[str] = set()
        self._stubbed = False
        self._origin: dict[str, str] = {}
        self._audit_findings: dict[str, Any] = {}
        self._audit_warnings: list[str] = []

    async def _io(self, fn, *args):
        return await asyncio.to_thread(fn, *args)

    # ------------------------------------------------------------------ lifecycle
    async def execute(self, run: Run) -> Run:
        s = self.settings
        self.run = run
        self.ctx = RunContext(
            case_id=run.case_id, run_id=run.id, snapshot_id=None, as_of_date=None,
            mode=run.mode or RunMode.LIVE, model=None,
            budget=RunBudget(max_cost_usd=s.max_run_cost_usd, max_seconds=s.max_run_seconds,
                             deadline=time.monotonic() + s.max_run_seconds))
        started = time.monotonic()
        failure: RunFailure | None = None
        try:
            await asyncio.wait_for(self._body(), timeout=s.max_run_seconds)
        except TimeoutError:
            failure = RunTimeout(f"The run exceeded the time limit of {s.max_run_seconds} seconds")
        except RunFailure as exc:
            failure = exc
        except asyncio.CancelledError:
            await self._close(RunFailure("The server stopped while this run was in progress. "
                                         "Start the run again.", code="run_interrupted",
                                         retryable=True), started)
            raise
        except Exception as exc:
            logger.exception("Unexpected error in run %s", run.id)
            failure = RunFailure(f"Unexpected error in stage '{self._stage.value if self._stage else 'start'}'"
                                 f" ({type(exc).__name__})", code="internal_error")
        return await self._close(failure, started)

    async def _enter(self, stage: RunStage) -> None:
        self._end_stage()
        self._stage, self._stage_started = stage, time.monotonic()
        self.run = self.run.model_copy(update={"status": RunStatus.RUNNING, "stage": stage})
        self.ctx.trace.log(stage, "start")
        await self._io(self.repo.update_run, self.run)

    def _end_stage(self) -> None:
        if self._stage is not None and self._stage_started is not None:
            ms = int((time.monotonic() - self._stage_started) * 1000)
            self._durations[self._stage.value] = self._durations.get(self._stage.value, 0) + ms
            self._stage_started = None

    async def _close(self, failure: RunFailure | None, started: float) -> Run:
        self._end_stage()
        ctx = self.ctx
        durations = {**self._durations, "total": int((time.monotonic() - started) * 1000)}
        records = ctx.trace.usage
        ok = [u for u in records if u.get("outcome") == "ok"]
        tokens_known = bool(ok) and all(u["input_tokens"] is not None and u["output_tokens"] is not None
                                        for u in ok)
        usage = Usage(calls=len(records),
                      input_tokens=sum(u["input_tokens"] for u in ok) if tokens_known else None,
                      output_tokens=sum(u["output_tokens"] for u in ok) if tokens_known else None)
        b = ctx.budget
        cost = None if (not ok or b.cost_unavailable) else round(b.spent_cost_usd, 6)
        prompt_versions = {u["prompt_id"]: u["prompt_version"] for u in records if u.get("prompt_version")}
        cfg = self.settings.public_config()
        update: dict[str, Any] = {
            "usage": usage, "latency_ms": durations, "cost_usd": cost,
            "model_version": self.settings.llm_model if ctx.model is not None else "stub",
            "prompt_versions": prompt_versions, "config_version": config_version(cfg),
            "warnings": list(dict.fromkeys([*self.run.warnings, *ctx.warnings]))}
        if failure is None:
            update.update(status=RunStatus.COMPLETED, stage=RunStage.FINALIZE,
                          report_version=self._report_version, error=None)
        else:
            update.update(status=RunStatus.FAILED, error=failure.to_error_body())
        self.run = self.run.model_copy(update=update)
        trace = scrub({
            "run_id": self.run.id, "case_id": self.run.case_id, "trace_id": self.run.trace_id,
            "status": self.run.status.value, "error": failure.to_error_body().model_dump() if failure else None,
            "mode": (self.run.mode.value if self.run.mode else None),
            "parent_report_id": self.run.parent_report_id, "snapshot_id": self._snapshot_id,
            "report_version": self._report_version, "config": cfg,
            "config_version": update["config_version"], "model": update["model_version"],
            "modules": self._origin,
            "prompt_versions": prompt_versions, "stage_durations_ms": durations,
            "usage": records, "events": ctx.trace.events, "warnings": update["warnings"],
            "cost_usd": cost, "cost_note": None if cost is not None else "unavailable",
        }, secrets=[self.settings.llm_api_key, self.settings.api_shared_secret])
        await self._io(self.repo.save_trace, self.run.id, trace)
        await self._io(self.repo.update_run, self.run)
        return self.run

    # ------------------------------------------------------------------ stages
    async def _body(self) -> None:
        await self._enter(RunStage.VALIDATE)
        case, parent, modules = await self._validate()
        self.ctx.as_of_date = case.as_of_date
        await self._enter(RunStage.RETRIEVE)
        pack = await self._retrieve(case, parent, modules)
        await self._enter(RunStage.ANALYZE)
        results = await self._analyze_all(case, pack, modules)
        await self._enter(RunStage.AUDIT)
        audit = await self._audit_and_repair(case, pack, modules, results)
        await self._enter(RunStage.SYNTHESIZE)
        decision = await self._track(RoleId.CHAIR,
            lambda: self._synthesize(case, pack, modules, results, audit),
            lambda decision: results.get(RoleId.CHAIR) or RoleResult(role_id=RoleId.CHAIR,
                summary="Committee synthesis output", position=decision.recommendation.value,
                section_content=[SectionContent(key="recommendation",
                    summary="Committee synthesis output",
                    structured_data={"synthesis": decision.model_dump(mode="json")})]))
        await self._enter(RunStage.FINALIZE)
        await self._finalize(case, pack, parent, results, decision)

    async def _validate(self):
        s, run = self.settings, self.run
        case = await self._io(self.repo.get_case, run.case_id)
        if case is None:
            raise ValidationFailed("The case no longer exists", code="case_not_found")
        parent = None
        if run.parent_report_id:
            parent = await self._io(self.repo.get_report_by_id, run.parent_report_id)
            if parent is None or parent.case_id != run.case_id:
                raise ValidationFailed("parent_report_id is not a report of this case",
                                       code="incompatible_parent_report")
        modules = self._modules_factory()
        self._origin = dict(modules.origin)
        stubbed = sorted(n for n, o in modules.origin.items() if o == STUB_ORIGIN)
        self._stubbed = bool(stubbed)
        real_model_users = [n for n, o in modules.origin.items()
                            if o != STUB_ORIGIN and n != "import_document"]
        if not s.dev_stubs or real_model_users:  # real agents/chair need the LLM adapter
            if s.llm_provider.lower() == "placeholder":
                raise ProviderAuthError("The LLM provider is not configured (set LLM_PROVIDER and LLM_API_KEY)")
            try:
                self.ctx.model = self._llm_factory()
            except ValueError as exc:
                raise ProviderAuthError(str(exc)) from exc
        if stubbed:
            if not s.dev_stubs:
                raise ValidationFailed("Stub modules are only allowed in synthetic development mode",
                                       code="stubs_not_allowed")
            self.ctx.warnings.append("SYNTHETIC DEVELOPMENT MODE: stubbed modules: " + ", ".join(stubbed)
                                     + "; this is not a real analysis")
        return case, parent, modules

    async def _retrieve(self, case: CaseInput, parent: Report | None, modules: Modules) -> EvidencePack:
        run, ctx = self.run, self.ctx
        user_sources, user_evidence = await self._io(self.repo.list_user_evidence, run.case_id)
        retrieval_stubbed = modules.origin.get("build_evidence_pack") == STUB_ORIGIN
        if ctx.mode == RunMode.EVIDENCE_ONLY and not retrieval_stubbed:
            base = EvidencePack(sources=[], evidence=[], retrieval_warnings=[], snapshot_id="tmp",
                                synthetic=False)  # evidence-only: no network retrieval at all
        else:
            base = await self._module("evidence retrieval", modules.build_evidence_pack, case, ctx,
                                      cls=SourceOutage, code="source_outage")
            if not isinstance(base, EvidencePack):
                raise SourceOutage("Evidence retrieval returned an invalid result")
            if not base.evidence and base.retrieval_warnings and not user_evidence and parent is None:
                raise SourceOutage("Evidence sources are unavailable ("
                                   + base.retrieval_warnings[0][:200]
                                   + "); this is NOT a confirmed absence of data")
        ctx.warnings.extend(f"Retrieval: {w}"[:300] for w in base.retrieval_warnings)

        parent_src = list(parent.sources) if parent else []
        parent_ev = list(parent.evidence) if parent else []
        new_src = [*user_sources, *base.sources]
        new_ev = [*user_evidence, *base.evidence]
        known = {x.id for x in parent_src}
        if case.as_of_date:  # evidence without a known date is NOT allowed in a historical case
            bad = {x.id for x in new_src if x.id not in known
                   and (x.published_at is None or x.published_at > case.as_of_date)}
            if bad:
                ctx.warnings.append(f"{len(bad)} source(s) excluded: no publication date on or "
                                    f"before {case.as_of_date.isoformat()}")
            new_src = [x for x in new_src if x.id not in bad]
            new_ev = [x for x in new_ev if x.source_id not in bad]
        sources = _merge([*parent_src, *new_src], "Source")
        evidence = _merge([*parent_ev, *new_ev], "Evidence")
        if self._stubbed and any(not x.synthetic for x in sources):
            raise ValidationFailed("With stubbed modules only synthetic evidence is allowed",
                                   code="dev_stubs_requires_synthetic_evidence")
        if not evidence and not retrieval_stubbed and ctx.mode == RunMode.EVIDENCE_ONLY:
            raise ValidationFailed("An evidence-only run needs at least one evidence item "
                                   "(add evidence or upload a document first)", code="no_evidence")
        pack = EvidencePack(sources=sources, evidence=evidence,
                            retrieval_warnings=list(base.retrieval_warnings),
                            snapshot_id=f"snap-{run.id}",
                            synthetic=bool(sources) and all(x.synthetic for x in sources))
        try:
            integrity.assert_pack(pack)
        except integrity.IntegrityError as exc:
            raise ValidationFailed("Invalid evidence pack: " + "; ".join(exc.problems)) from exc
        await self._io(self.repo.save_snapshot, run.case_id, pack)
        self._snapshot_id = ctx.snapshot_id = pack.snapshot_id
        return pack

    # ------------------------------------------------------------------ analyze
    async def _module(self, name: str, fn, *args, cls=RunFailure, code="agent_error"):
        try:
            return await fn(*args)
        except (RunFailure, asyncio.CancelledError):
            raise
        except Exception as exc:
            logger.exception("Module step '%s' failed", name)
            if cls is SourceOutage:
                raise SourceOutage(f"Evidence retrieval failed ({type(exc).__name__}); this is NOT a "
                                   "confirmed absence of data") from exc
            raise RunFailure(f"The {name} step failed ({type(exc).__name__})", code=code) from exc

    async def _agent(self, role: RoleId, factory) -> RoleResult:
        async def invoke():
            result = await self._module(f"{role.value} analysis", factory)
            if not isinstance(result, RoleResult):
                raise RunFailure(f"The {role.value} analysis returned an invalid result", code="agent_error")
            if result.role_id != role:
                raise ValidationFailed(f"The {role.value} analysis returned role_id '{result.role_id.value}'")
            return result
        return await self._track(role, invoke)

    async def _save_node(self, role, status, *, result=None, error=None):
        if not hasattr(self, "_node_states"):
            self._node_states = {}
        previous = self._node_states.get(role, NodeOutput(role_id=role))
        node = previous.model_copy(update={"status": status, "stage": self._stage,
            "attempt": previous.attempt + (1 if status == "running" else 0),
            "result": result if result is not None else previous.result, "error": error,
            "stale": False if status == "completed" else previous.result is not None})
        await self._io(self.repo.save_node, self.run.id, node)
        self._node_states[role] = node

    async def _track(self, role, factory, serialize=lambda result: result):
        await self._save_node(role, "running")
        try:
            result = await factory()
            output = serialize(result)
        except asyncio.CancelledError:
            await self._save_node(role, "interrupted", error=ErrorBody(
                code="node_interrupted", message="This node stopped before completing.", retryable=True))
            raise
        except Exception as exc:
            error = (ErrorBody(code=exc.code, message=str(exc), retryable=exc.retryable)
                     if isinstance(exc, RunFailure) else ErrorBody(code="node_error",
                         message=f"The {role.value} node failed ({type(exc).__name__})."))
            error = error.model_copy(update={"message": scrub(error.message,
                secrets=[self.settings.llm_api_key, self.settings.api_shared_secret])})
            await self._save_node(role, "failed", error=error)
            raise
        await self._save_node(role, "completed", result=output)
        return result

    async def _gather(self, coros: list):
        if not coros:
            return []
        tasks = [asyncio.ensure_future(c) for c in coros]
        try:
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for t in tasks:
                if t.done() and not t.cancelled() and t.exception() is not None:
                    raise t.exception()
            return [t.result() for t in tasks]
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _run_roles(self, roles: set[RoleId], results: dict[RoleId, RoleResult],
                         case: CaseInput, pack: EvidencePack, modules: Modules) -> None:
        ctx = self.ctx
        first = {RoleId.SCIENCE: lambda: modules.analyze_science(case, pack, ctx),
                 RoleId.TRANSLATION: lambda: modules.analyze_translation(case, pack, ctx)}
        todo = [r for r in first if r in roles]
        outs = await self._gather([self._agent(r, first[r]) for r in todo])
        results.update(dict(zip(todo, outs)))
        if RoleId.CLINICAL in roles:
            results[RoleId.CLINICAL] = await self._agent(RoleId.CLINICAL, lambda: call_clinical(
                modules.analyze_clinical, case, pack, results[RoleId.SCIENCE],
                results[RoleId.TRANSLATION], ctx))
        if RoleId.MARKET in roles:
            kwargs = {"clinical": results[RoleId.CLINICAL]} if "clinical" in inspect.signature(modules.analyze_market).parameters else {}
            results[RoleId.MARKET] = await self._agent(RoleId.MARKET,
                lambda: modules.analyze_market(case, pack, ctx, **kwargs))
        for role, name, inputs in [
            (RoleId.IP_LICENSING, "analyze_ip_licensing", ("science", "clinical", "market")),
            (RoleId.PARTNERSHIPS, "analyze_partnerships", ("science", "clinical", "market", "ip_licensing")),
        ]:
            if role in roles:
                fn = getattr(modules, name)
                upstream = {key: results[RoleId(key)] for key in inputs}
                results[role] = await self._agent(role, lambda fn=fn, upstream=upstream:
                    fn(case, pack, ctx, **upstream))
        if RoleId.INVESTMENT in roles:
            results[RoleId.INVESTMENT] = await self._agent(RoleId.INVESTMENT, lambda: call_investment(
                modules.analyze_investment, case, pack, results[RoleId.CLINICAL], results[RoleId.MARKET], ctx,
                partnerships=results[RoleId.PARTNERSHIPS], ip_licensing=results[RoleId.IP_LICENSING]))
        for role, name in [(RoleId.INVESTMENT_THRESHOLD, "analyze_investment_threshold"),
                           (RoleId.FAILURE_MINER, "analyze_failure_miner")]:
            if role in roles:
                fn = getattr(modules, name)
                upstream = {r.value: results[r] for r in ROLE_ORDER[:ROLE_ORDER.index(role)]}
                results[role] = await self._agent(role, lambda fn=fn, upstream=upstream:
                    fn(case, pack, ctx, **upstream))

    async def _analyze_all(self, case, pack, modules) -> dict[RoleId, RoleResult]:
        results: dict[RoleId, RoleResult] = {}
        await self._run_roles(set(ROLE_ORDER), results, case, pack, modules)
        self._collect_claims(results, pack)  # fail fast on dangling evidence / duplicate claims
        return results

    def _collect_claims(self, results: dict[RoleId, RoleResult], pack: EvidencePack) -> list[Claim]:
        evidence_ids = {e.id for e in pack.evidence}
        merged: dict[str, Claim] = {}
        for role in ROLE_ORDER:
            for c in (results[role].claims if role in results else []):
                if c.id in merged and merged[c.id] != c:
                    raise ValidationFailed(f"Claim '{c.id}' was produced twice with different content",
                                           code="duplicate_claim_id")
                for eid in c.evidence_ids:
                    if eid not in evidence_ids:
                        raise ValidationFailed(f"Claim '{c.id}' cites unknown evidence '{eid}'",
                                               code="dangling_evidence")
                merged.setdefault(c.id, c)
        return list(merged.values())

    # ------------------------------------------------------------------ audit
    @staticmethod
    def _blocking(audit: AuditResult, ids: set[str]) -> set[str]:
        found = set(audit.unresolved_critical_claim_ids) | {f.claim_id for f in audit.findings if f.blocking}
        return found & ids

    async def _audit(self, claims: list[Claim], pack: EvidencePack, modules: Modules) -> AuditResult:
        def serialize(audit):
            summary = f"Audit returned {len(audit.findings)} findings."
            return RoleResult(role_id=RoleId.AUDIT, summary=summary,
                position="Audit output; review may still be required", unknowns=audit.warnings,
                section_content=[SectionContent(key="sources", summary=summary,
                    structured_data={"findings": [finding.model_dump(mode="json")
                        for finding in self._audit_findings.values()],
                        "unresolved_critical_claim_ids": sorted(set(audit.unresolved_critical_claim_ids) | self._unresolved),
                        "warnings": audit.warnings})])
        return await self._track(RoleId.AUDIT,
            lambda: self._audit_untracked(claims, pack, modules), serialize)

    async def _audit_untracked(self, claims, pack, modules):
        documents = await self._io(self.repo.list_documents, self.run.case_id)
        async def invoke():
            return await call_audit(modules.audit_claims, claims, pack, self.ctx, documents=documents)
        audit = await self._module("claim audit", invoke, code="audit_error")
        if not isinstance(audit, AuditResult):
            raise RunFailure("The claim audit returned an invalid result", code="audit_error")
        self.ctx.warnings.extend(f"Audit: {w}"[:300] for w in audit.warnings)
        self._audit_findings.update({finding.claim_id: finding for finding in audit.findings})
        self._audit_warnings.extend(audit.warnings)
        return audit

    def _downgrade(self, results: dict[RoleId, RoleResult], ids: set[str]) -> None:
        for role, res in list(results.items()):
            claims = [c.model_copy(update={"support_status": SupportStatus.UNVERIFIED})
                      if c.id in ids and c.support_status in _NEEDS_EVIDENCE else c for c in res.claims]
            results[role] = res.model_copy(update={"claims": claims})

    async def _audit_and_repair(self, case, pack, modules, results) -> AuditResult:
        claims = self._collect_claims(results, pack)
        ids = {c.id for c in claims}
        audit = await self._audit(claims, pack, modules)
        problem = self._blocking(audit, ids)
        if problem:  # ONE subject-level repair: only the owners of the blocked claims (+ dependents)
            owners = {r for r, res in results.items() if {c.id for c in res.claims} & problem}
            for role in owners:
                self.ctx.feedback[role.value] = [f for f in audit.findings if f.claim_id in
                                                 {c.id for c in results[role].claims}]
            self.ctx.trace.log(RunStage.AUDIT, f"repair round for roles {sorted(r.value for r in owners)}")
            affected = _expand(owners)
            await self._save_node(RoleId.AUDIT, "stale")
            for role in affected:
                if role in results:
                    await self._save_node(role, "stale")
            await self._run_roles(affected, results, case, pack, modules)
            claims = self._collect_claims(results, pack)
            ids = {c.id for c in claims}
            audit = await self._audit(claims, pack, modules)
        remaining = self._blocking(audit, ids)
        if remaining:
            self._downgrade(results, remaining)
            claims = self._collect_claims(results, pack)
            self._unresolved |= {c.id for c in claims if c.id in remaining and c.importance == Importance.CRITICAL}
            self.ctx.warnings.append("These claims could not be verified by the audit and were set to "
                                     "'unverified': " + ", ".join(sorted(remaining)))
        for role, result in results.items():
            await self._save_node(role, "completed", result=result)
        return audit

    # ------------------------------------------------------------------ chair
    @staticmethod
    def _completeness(decision: CommitteeDecision, known_ids: set[str]) -> list[str]:
        issues = []
        if not 5 <= len(decision.questions) <= 10:
            issues.append(f"Provide 5-10 diligence questions (got {len(decision.questions)}).")
        for c in decision.additional_claims:
            if c.id in known_ids:
                issues.append(f"Additional claim id '{c.id}' already exists; use a new stable key.")
        return issues

    async def _synthesize(self, case, pack, modules, results, audit) -> CommitteeDecision:
        ctx = self.ctx
        ordered = [results[r] for r in ROLE_ORDER if r in results]
        known = {c.id for res in ordered for c in res.claims}

        async def chair() -> CommitteeDecision:
            kwargs = {"case": case, "pack": pack} if "case" in inspect.signature(modules.synthesize_committee).parameters else {}
            async def invoke():
                return await modules.synthesize_committee(ordered, audit, ctx, **kwargs)
            d = await self._module("committee synthesis", invoke)
            from vic.agents.business.chair import ChairResult
            if isinstance(d, ChairResult):
                results[RoleId.CHAIR] = d.role_result
                d = d.decision
            if not isinstance(d, CommitteeDecision):
                raise RunFailure("The committee synthesis returned an invalid result", code="agent_error")
            return d

        async def check(d: CommitteeDecision):
            issues = self._completeness(d, known)
            blocked: set[str] = set()
            if d.additional_claims:
                ev = {e.id for e in pack.evidence}
                for c in d.additional_claims:
                    for eid in c.evidence_ids:
                        if eid not in ev:
                            issues.append(f"Claim '{c.id}' cites unknown evidence '{eid}'.")
                chair_audit = await self._audit(d.additional_claims, pack, modules)  # R3 checks new claims
                blocked = self._blocking(chair_audit, {c.id for c in d.additional_claims})
                issues += [f"Claim '{x}' was blocked by the evidence audit." for x in sorted(blocked)]
            return issues, blocked

        decision = await chair()
        issues, blocked = await check(decision)
        if issues:  # ONE repair round for the chair
            ctx.feedback["chair"] = list(issues)
            ctx.trace.log(RunStage.SYNTHESIZE, "repair round for chair")
            decision = await chair()
            issues, blocked = await check(decision)
        if issues and not blocked:
            raise ValidationFailed("The committee output is incomplete: " + " ".join(issues),
                                   code="incomplete_committee_output")
        if blocked:
            extra = [c.model_copy(update={"support_status": SupportStatus.UNVERIFIED})
                     if c.id in blocked and c.support_status in _NEEDS_EVIDENCE else c
                     for c in decision.additional_claims]
            decision = decision.model_copy(update={"additional_claims": extra})
            self._unresolved |= {c.id for c in extra if c.id in blocked and c.importance == Importance.CRITICAL}
            ctx.warnings.append("Chair claims set to 'unverified' after the audit: " + ", ".join(sorted(blocked)))
        if self._unresolved and decision.recommendation == Recommendation.INVEST:
            decision = decision.model_copy(update={
                "recommendation": Recommendation.CONDITIONAL,
                "conditions": [*decision.conditions, "Recommendation lowered to Conditional: critical claims "
                               "could not be verified: " + ", ".join(sorted(self._unresolved))]})
        if RoleId.CHAIR in results:
            role = results[RoleId.CHAIR]
            sections = []
            for section in role.section_content:
                data = dict(section.structured_data or {})
                rich = dict(data.get("chair", {}))
                rich["committee_decision"] = decision.model_dump(mode="json")
                rich["recommendation"] = decision.recommendation.value
                data["chair"] = rich
                sections.append(section.model_copy(update={"structured_data": data}))
            results[RoleId.CHAIR] = role.model_copy(update={"claims": decision.additional_claims,
                "position": decision.recommendation.value, "section_content": sections})
        return decision

    # ------------------------------------------------------------------ finalize
    async def _finalize(self, case, pack, parent, results, decision) -> None:
        run = self.run
        roles = [results[r] for r in ROLE_ORDER if r in results]
        if RoleId.CHAIR in results:
            roles.append(results[RoleId.CHAIR])
        claims = self._collect_claims(results, pack)
        have = {c.id for c in claims}
        for c in decision.additional_claims:
            if c.id not in have:
                claims.append(c)
        audited_claims = [claim for claim in claims if claim.id in self._audit_findings]
        findings = [self._audit_findings[claim.id].model_dump(mode="json") for claim in audited_claims]
        audit_summary = f"Checked {len(audited_claims)} claims; {len(self._unresolved)} unresolved critical claims."
        roles.append(RoleResult(role_id=RoleId.AUDIT, summary=audit_summary,
            position="Review required" if self._unresolved else "Audit completed with limitations",
            claims=audited_claims, unknowns=list(dict.fromkeys(self._audit_warnings)),
            section_content=[SectionContent(key="sources", summary=audit_summary,
                claim_ids=[claim.id for claim in audited_claims],
                limitations=["Automated audit is not independent expert verification."],
                structured_data={"findings": findings,
                                 "unresolved_critical_claim_ids": sorted(self._unresolved)})]))
        report_id = new_id("rep")

        def make(version: int) -> Report:
            return build_report(case=case, pack=pack, roles=roles, decision=decision, claims=claims,
                                case_id=run.case_id, run_id=run.id, report_id=report_id,
                                version=version, parent=parent,
                                synthetic=True if self._stubbed else None)

        try:
            integrity.assert_report(make(parent.version + 1 if parent else 1), parent=parent)
            saved = await self._io(self.repo.save_next_report, run.case_id, make)
        except integrity.IntegrityError as exc:
            raise ValidationFailed("The report failed validation: " + "; ".join(exc.problems[:5]),
                                   code="validation_failed") from exc
        except ValidationError as exc:
            raise ValidationFailed("The assembled report does not match the contract "
                                   f"({exc.error_count()} error(s))", code="validation_failed") from exc
        except ReportExistsError as exc:
            raise RunFailure("Another run saved a report for this case at the same time; start again",
                             code="version_conflict", retryable=True) from exc
        self._report_version = saved.version
