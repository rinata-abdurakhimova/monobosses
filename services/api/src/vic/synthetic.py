"""Fully synthetic fixtures for contract v1. No real drug, target or disease.

`build_all()` is the single source of truth: scripts/generate_fixtures.py writes it to
contracts/fixtures/*.json, and the mock repository serves the same objects.
Story: v1 = Conditional (safe exposure unknown); v2 = Do Not Invest (synthetic safety result).
"""
import hashlib
from datetime import UTC, date, datetime

from pydantic import BaseModel

from vic import integrity
from vic.contracts import (
    CaseInput,
    Claim,
    ClaimChange,
    DiligenceQuestion,
    Disagreement,
    ErrorBody,
    Evidence,
    EvidencePack,
    Importance,
    Provenance,
    Recommendation,
    Report,
    Revision,
    Risk,
    RoleId,
    RoleResult,
    Run,
    RunMode,
    RunStage,
    RunStatus,
    Scope,
    SectionContent,
    SectionKey,
    Source,
    SupportStatus,
)

CASE_ID = "case-synthetic-01"
REPORT_V1_ID = "rep-synthetic-v1"
REPORT_V2_ID = "rep-synthetic-v2"
SNAPSHOT_V1 = "snap-synthetic-v1"
SNAPSHOT_V2 = "snap-synthetic-v2"
RETRIEVED_AT = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
RETRIEVED_AT_V2 = datetime(2025, 6, 10, 12, 0, 0, tzinfo=UTC)

# ------------------------------------------------------------------ sources & evidence
_TEXTS = {
    "src-synthetic-01": (
        "Синтетичне дослідження повідомляє, що варіанти втрати функції гена мішені Y асоційовані "
        "зі зниженим ризиком захворювання X у синтетичній когорті. Асоціація не доводить причинності."),
    "src-synthetic-02": (
        "У синтетичній тваринній моделі інгібування мішені Y зменшувало маркер прогресування X. "
        "Модель лише частково відтворює захворювання людини."),
    "src-synthetic-03": (
        "Синтетичний запис реєстру: дослідження фази 1 синтетичного кандидата заплановане; "
        "первинна кінцева точка — безпека та переносимість; експозицію в пацієнтів не повідомлено."),
    "src-synthetic-04": (
        "Синтетична презентація компанії заявляє про намір розпочати фазу 2 після підтвердження "
        "безпеки. Це матеріал компанії, не незалежний доказ."),
    "src-synthetic-05": (
        "Синтетичний звіт про дослідження фази 1: при експозиції, потрібній для дії на мішень, "
        "зафіксовано серйозну небажану подію, що зупинило підвищення дози."),
}

# (id, title, type, published_at)
_SOURCE_SPECS = [
    ("src-synthetic-01", "[SYNTHETIC] Стаття: генетична асоціація мішені Y із захворюванням X",
     "peer_reviewed", date(2022, 3, 15)),
    ("src-synthetic-02", "[SYNTHETIC] Препринт: доклінічна модель інгібування мішені Y",
     "preprint", date(2023, 5, 2)),
    ("src-synthetic-03", "[SYNTHETIC] Запис реєстру клінічних досліджень", "registry",
     date(2024, 9, 1)),
    ("src-synthetic-04", "[SYNTHETIC] Презентація компанії-розробника", "company",
     date(2024, 11, 20)),
]
_SOURCE_SPEC_V2 = ("src-synthetic-05", "[SYNTHETIC] Звіт про безпеку дослідження фази 1",
                   "company", date(2025, 6, 1))

# (id, source_id, excerpt, locator, scope, limitations) — excerpt must be a substring of the text
_EVIDENCE_SPECS = [
    ("ev-synthetic-01", "src-synthetic-01",
     "варіанти втрати функції гена мішені Y асоційовані зі зниженим ризиком захворювання X",
     "abstract", Scope.APPROACH, ["Синтетична когорта; причинність не встановлена"]),
    ("ev-synthetic-02", "src-synthetic-01", "Асоціація не доводить причинності.", "limitations",
     Scope.APPROACH, []),
    ("ev-synthetic-03", "src-synthetic-02",
     "інгібування мішені Y зменшувало маркер прогресування X", "results", Scope.APPROACH,
     ["Тваринна модель частково відтворює захворювання людини"]),
    ("ev-synthetic-04", "src-synthetic-03", "експозицію в пацієнтів не повідомлено",
     "record.results", Scope.PROGRAM, []),
    ("ev-synthetic-05", "src-synthetic-03", "первинна кінцева точка — безпека та переносимість",
     "record.endpoints", Scope.PROGRAM, []),
    ("ev-synthetic-06", "src-synthetic-04", "Це матеріал компанії, не незалежний доказ.",
     "slide 5", Scope.PROGRAM, ["Матеріал компанії"]),
]
_EVIDENCE_SPEC_V2 = (
    "ev-synthetic-07", "src-synthetic-05",
    "зафіксовано серйозну небажану подію, що зупинило підвищення дози", "section 3",
    Scope.PROGRAM, ["Синтетичний результат для контрольованої історії v1 → v2"])


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sources(specs, retrieved_at):
    return [Source(id=i, title=t, url=None, type=ty, published_at=d, retrieved_at=retrieved_at,
                   content_hash=_hash(_TEXTS[i]), synthetic=True) for i, t, ty, d in specs]


def _evidence(specs):
    for _id, src, excerpt, *_ in specs:
        if excerpt not in _TEXTS[src]:
            raise AssertionError(f"excerpt of {_id} is not a substring of {src}")
    return [Evidence(id=i, source_id=s, excerpt=x, locator=loc, scope=sc, limitations=lim)
            for i, s, x, loc, sc, lim in specs]


def build_pack_v1() -> EvidencePack:
    return EvidencePack(
        sources=_sources(_SOURCE_SPECS, RETRIEVED_AT), evidence=_evidence(_EVIDENCE_SPECS),
        retrieval_warnings=["Синтетичний пакет: мережеве отримання джерел не виконувалось."],
        snapshot_id=SNAPSHOT_V1, synthetic=True)


def build_pack_v2() -> EvidencePack:
    v1 = build_pack_v1()
    return EvidencePack(
        sources=v1.sources + _sources([_SOURCE_SPEC_V2], RETRIEVED_AT_V2),
        evidence=v1.evidence + _evidence([_EVIDENCE_SPEC_V2]),
        retrieval_warnings=v1.retrieval_warnings, snapshot_id=SNAPSHOT_V2, synthetic=True)


# ------------------------------------------------------------------ case
def build_case() -> CaseInput:
    return CaseInput(
        indication="Синтетичне захворювання X",
        mechanism="Інгібування синтетичної мішені Y",
        scope=Scope.PROGRAM,
        program_data=("Синтетична програма: пероральна мала молекула, що інгібує мішень Y; "
                      "доклінічні дані обмежені; даних про експозицію в людини немає."),
        modality="мала молекула", development_stage="Підготовка до фази 1", as_of_date=None)


# ------------------------------------------------------------------ claims
def _claim(id_, text, prov, status, ev, scope, imp):
    return Claim(id=id_, text=text, provenance=prov, support_status=status, evidence_ids=ev,
                 assumptions=[], scope=scope, importance=imp)


def _claims_v1() -> list[Claim]:
    P, S, I = Provenance, SupportStatus, Importance
    return [
        _claim("science.target_validation",
               "Генетичні дані пов'язують втрату функції мішені Y зі зниженим ризиком X, "
               "але це асоціація, а не доведена причинність.",
               P.SOURCE, S.MIXED, ["ev-synthetic-01", "ev-synthetic-02"], Scope.APPROACH, I.CRITICAL),
        _claim("science.animal_model",
               "Тваринна модель показує зменшення маркера прогресування, але її релевантність "
               "для людини обмежена.",
               P.SOURCE, S.MIXED, ["ev-synthetic-03"], Scope.APPROACH, I.MAJOR),
        _claim("translation.safe_exposure",
               "Безпечність потрібної експозиції у людини не встановлено.",
               P.AI, S.UNKNOWN, ["ev-synthetic-04"], Scope.PROGRAM, I.CRITICAL),
        _claim("translation.biomarker_link",
               "Біомаркер, що пов'язує дію на мішень із користю для пацієнта, не підтверджений.",
               P.AI, S.UNVERIFIED, [], Scope.PROGRAM, I.MAJOR),
        _claim("clinical.phase1_design",
               "Заплановане дослідження фази 1 орієнтоване на безпеку та переносимість.",
               P.SOURCE, S.SUPPORTED, ["ev-synthetic-05"], Scope.PROGRAM, I.MAJOR),
        _claim("clinical.efficacy_path",
               "Шлях до доказів ефективності залежить від результатів безпеки і не визначений.",
               P.AI, S.UNKNOWN, [], Scope.PROGRAM, I.MAJOR),
        _claim("market.company_claims",
               "Заяви компанії про наміри не є незалежним доказом комерційної цінності.",
               P.SOURCE, S.SUPPORTED, ["ev-synthetic-06"], Scope.PROGRAM, I.MINOR),
        _claim("market.unmet_need",
               "Незадоволена потреба при X потребує перевірки за незалежними джерелами.",
               P.AI, S.UNVERIFIED, [], Scope.APPROACH, I.MAJOR),
        _claim("investment.capital_unknown",
               "Капітал до наступного milestone неможливо обґрунтувати без бюджету й плану "
               "дослідження.",
               P.AI, S.UNKNOWN, [], Scope.PROGRAM, I.MAJOR),
        _claim("user.program_summary",
               "Користувач надав опис синтетичної програми; його не перевірено незалежно.",
               P.USER, S.UNVERIFIED, [], Scope.PROGRAM, I.MINOR),
    ]


def _claims_v2() -> list[Claim]:
    claims = _claims_v1()
    for i, c in enumerate(claims):
        if c.id == "translation.safe_exposure":
            claims[i] = _claim(
                "translation.safe_exposure",
                "Потрібна експозиція у людини небезпечна: у синтетичному дослідженні зафіксовано "
                "серйозну небажану подію.",
                Provenance.SOURCE, SupportStatus.CONTRADICTED,
                ["ev-synthetic-04", "ev-synthetic-07"], Scope.PROGRAM, Importance.CRITICAL)
    return claims


# ------------------------------------------------------------------ risks, questions, sections
def _risks(v2: bool) -> list[Risk]:
    r1 = (Risk(id="risk-synthetic-01",
               description="Підтверджено серйозну небажану подію при потрібній експозиції.",
               priority=Importance.CRITICAL, claim_ids=["translation.safe_exposure"],
               impact="Теза програми не виконується без іншого режиму дозування або кандидата.",
               next_check="Перевірити, чи існує альтернативний режим або кандидат.")
          if v2 else
          Risk(id="risk-synthetic-01",
               description="Безпечність потрібної експозиції у людини не встановлена.",
               priority=Importance.CRITICAL, claim_ids=["translation.safe_exposure"],
               impact="Може зупинити розробку й зробити інвестиційну тезу недійсною.",
               next_check="Отримати дані безпеки та експозиції з дослідження фази 1."))
    return [
        r1,
        Risk(id="risk-synthetic-02",
             description="Ефект у тваринній моделі може не відтворитися у людини.",
             priority=Importance.MAJOR, claim_ids=["science.animal_model"],
             impact="Знижує наукову обґрунтованість механізму для людини.",
             next_check="Знайти дані на людських тканинах або біомаркерні дані."),
        Risk(id="risk-synthetic-03",
             description="Невідомий бюджет і час до наступного milestone.",
             priority=Importance.MAJOR, claim_ids=["investment.capital_unknown"],
             impact="Неможливо оцінити потребу у фінансуванні.",
             next_check="Отримати кошторис і план дослідження фази 1."),
    ]


def _questions(v2: bool) -> list[DiligenceQuestion]:
    q1 = (DiligenceQuestion(
        question="Чи існує режим дозування, що дає дію на мішень без серйозної небажаної події?",
        why_it_matters="Від цього залежить, чи можна повернутися до розгляду програми.",
        evidence_needed="Дані дозування та безпеки з наступних когорт.",
        decision_if_positive="Переглянути рекомендацію в бік Conditional.",
        decision_if_negative="Залишити Do Not Invest.")
        if v2 else DiligenceQuestion(
        question="Чи досягається потрібна експозиція в людини безпечно?",
        why_it_matters="Це критичне невідоме, що блокує тезу про користь для пацієнта.",
        evidence_needed="Дані PK та безпеки з дослідження фази 1.",
        decision_if_positive="Рекомендація може стати Invest за умови інших підтверджень.",
        decision_if_negative="Рекомендація стає Do Not Invest."))
    return [
        q1,
        DiligenceQuestion(
            question="Який біомаркер підтверджує дію на мішень у людини?",
            why_it_matters="Без нього ланцюг «ефект → користь» залишається розірваним.",
            evidence_needed="Біомаркерні дані з ранніх досліджень.",
            decision_if_positive="Підсилює тезу перенесення результатів на людину.",
            decision_if_negative="Знижує впевненість у механізмі."),
        DiligenceQuestion(
            question="Чи підтверджується генетична асоціація в незалежних когортах?",
            why_it_matters="Одна когорта не доводить причинності.",
            evidence_needed="Незалежні генетичні дослідження.",
            decision_if_positive="Підсилює наукову тезу.",
            decision_if_negative="Науковий аргумент слабшає."),
        DiligenceQuestion(
            question="Який бюджет і графік дослідження фази 1?",
            why_it_matters="Потрібен для оцінки капіталу до milestone.",
            evidence_needed="Кошторис CRO та план дослідження.",
            decision_if_positive="Дозволяє дати діапазон капіталу.",
            decision_if_negative="Діапазон не обґрунтовується; рішення лишається умовним."),
        DiligenceQuestion(
            question="Які існують альтернативи для пацієнтів із X і чим програма відрізняється?",
            why_it_matters="Комерційна цінність залежить від відмінності від стандарту лікування.",
            evidence_needed="Огляд стандарту лікування та конкурентних програм.",
            decision_if_positive="Підсилює комерційну тезу.",
            decision_if_negative="Знижує комерційну привабливість."),
        DiligenceQuestion(
            question="Чи є обмеження прав або ліцензій, що впливають на програму?",
            why_it_matters="Права третіх осіб можуть змінити умови угоди.",
            evidence_needed="Патентний пошук і висновок юриста.",
            decision_if_positive="Умови угоди можна обговорювати.",
            decision_if_negative="Потрібні ліцензії або змінюється структура угоди."),
    ]


_SUMMARIES_V1 = {
    SectionKey.RECOMMENDATION: "Conditional: інтерес залежить від підтвердження безпеки експозиції.",
    SectionKey.SCIENTIFIC_THESIS: "Є часткове генетичне та доклінічне обґрунтування мішені Y.",
    SectionKey.HUMAN_TRANSLATION_THESIS: "Безпечність потрібної експозиції у людини не встановлена.",
    SectionKey.CLINICAL_DEVELOPMENT_PLAN: "Фаза 1 орієнтована на безпеку; шлях до ефективності не визначено.",
    SectionKey.COMPETITIVE_LANDSCAPE: "Конкурентне середовище потребує незалежної перевірки.",
    SectionKey.COMMERCIAL_OPPORTUNITY: "Комерційна цінність не підтверджена незалежними джерелами.",
    SectionKey.CAPITAL_TO_MILESTONE: "Діапазон капіталу не оцінено: бракує бюджету й плану дослідження.",
    SectionKey.KEY_RISKS: "Критичний ризик — безпечність експозиції; суттєві — модель і бюджет.",
    SectionKey.CRITICAL_UNKNOWNS: "Безпечна експозиція, біомаркер, шлях до ефективності, бюджет.",
    SectionKey.DILIGENCE_QUESTIONS: "Шість пріоритетних питань для перевірки.",
    SectionKey.SOURCES: "Чотири синтетичні джерела; частина — матеріали компанії.",
}
_SUMMARIES_V2 = dict(_SUMMARIES_V1) | {
    SectionKey.RECOMMENDATION: "Do Not Invest: синтетичний результат показує небезпечну експозицію.",
    SectionKey.HUMAN_TRANSLATION_THESIS: "Потрібна експозиція супроводжується серйозною небажаною подією.",
    SectionKey.KEY_RISKS: "Критичний ризик підтверджено синтетичним результатом безпеки.",
    SectionKey.CRITICAL_UNKNOWNS: "Чи існує безпечний режим дозування; біомаркер; бюджет.",
    SectionKey.DILIGENCE_QUESTIONS: "Шість питань; перше стосується безпечного режиму.",
    SectionKey.SOURCES: "П'ять синтетичних джерел, включно зі звітом про безпеку.",
}

_SECTION_CLAIMS = {
    SectionKey.RECOMMENDATION: ["translation.safe_exposure"],
    SectionKey.SCIENTIFIC_THESIS: ["science.target_validation", "science.animal_model"],
    SectionKey.HUMAN_TRANSLATION_THESIS: ["translation.safe_exposure", "translation.biomarker_link"],
    SectionKey.CLINICAL_DEVELOPMENT_PLAN: ["clinical.phase1_design", "clinical.efficacy_path"],
    SectionKey.COMPETITIVE_LANDSCAPE: ["market.unmet_need"],
    SectionKey.COMMERCIAL_OPPORTUNITY: ["market.company_claims", "market.unmet_need"],
    SectionKey.CAPITAL_TO_MILESTONE: ["investment.capital_unknown"],
    SectionKey.KEY_RISKS: ["translation.safe_exposure", "science.animal_model",
                           "investment.capital_unknown"],
    SectionKey.CRITICAL_UNKNOWNS: ["translation.safe_exposure", "clinical.efficacy_path",
                                   "investment.capital_unknown"],
    SectionKey.DILIGENCE_QUESTIONS: ["translation.safe_exposure", "translation.biomarker_link"],
    SectionKey.SOURCES: [],
}
_SECTION_LIMITS = {
    SectionKey.SCIENTIFIC_THESIS: ["Асоціація не доводить причинності."],
    SectionKey.CAPITAL_TO_MILESTONE: ["Потрібні кошторис і план дослідження."],
    SectionKey.COMMERCIAL_OPPORTUNITY: ["Розмір популяції не прирівнюється до доступного ринку."],
}


def _sections(summaries, recommendation, risks, questions, sources) -> list[SectionContent]:
    out = []
    for key in SectionKey:
        data = None
        if key == SectionKey.RECOMMENDATION:
            data = {"recommendation": recommendation.value}
        elif key == SectionKey.KEY_RISKS:
            data = {"risk_ids": [r.id for r in risks]}
        elif key == SectionKey.DILIGENCE_QUESTIONS:
            data = {"question_count": len(questions)}
        elif key == SectionKey.SOURCES:
            data = {"source_ids": [s.id for s in sources]}
        out.append(SectionContent(key=key, summary=summaries[key],
                                  claim_ids=list(_SECTION_CLAIMS[key]),
                                  limitations=list(_SECTION_LIMITS.get(key, [])),
                                  structured_data=data))
    return out


def _roles(claims, risks, sections, v2: bool) -> list[RoleResult]:
    c = {x.id: x for x in claims}
    r = {x.id: x for x in risks}
    s = {x.key: x for x in sections}
    return [
        RoleResult(
            role_id=RoleId.SCIENCE, summary="Часткове біологічне обґрунтування.",
            position="Мішень Y має підтримку генетики й доклініки, причинність не доведена.",
            claims=[c["science.target_validation"], c["science.animal_model"]],
            risks=[r["risk-synthetic-02"]],
            unknowns=["Причинність генетичної асоціації"],
            change_conditions=["Незалежні когорти або дані на людських тканинах"],
            section_content=[s[SectionKey.SCIENTIFIC_THESIS]]),
        RoleResult(
            role_id=RoleId.TRANSLATION,
            summary=("Експозиція небезпечна." if v2 else "Безпечність експозиції не встановлена."),
            position=("Нове синтетичне свідчення спростовує безпечну експозицію." if v2 else
                      "Ланка «експозиція → безпека» відсутня; властивості кандидата не переносяться "
                      "на весь механізм."),
            claims=[c["translation.safe_exposure"], c["translation.biomarker_link"]],
            risks=[r["risk-synthetic-01"]],
            unknowns=["Біомаркер дії на мішень"],
            change_conditions=["Безпечний режим дозування"] if v2 else
            ["Дані PK та безпеки з дослідження фази 1"],
            section_content=[s[SectionKey.HUMAN_TRANSLATION_THESIS]]),
        RoleResult(
            role_id=RoleId.CLINICAL, summary="Фаза 1 запланована, далі невизначено.",
            position="Шлях до ефективності залежить від безпеки.",
            claims=[c["clinical.phase1_design"], c["clinical.efficacy_path"]], risks=[],
            unknowns=["Endpoints фази 2"], change_conditions=["Результати безпеки"],
            section_content=[s[SectionKey.CLINICAL_DEVELOPMENT_PLAN]]),
        RoleResult(
            role_id=RoleId.MARKET, summary="Комерційна цінність не підтверджена.",
            position="Заяви компанії не є незалежним доказом.",
            claims=[c["market.company_claims"], c["market.unmet_need"]], risks=[],
            unknowns=["Стандарт лікування й альтернативи"],
            change_conditions=["Незалежний огляд ринку"],
            section_content=[s[SectionKey.COMPETITIVE_LANDSCAPE],
                             s[SectionKey.COMMERCIAL_OPPORTUNITY]]),
        RoleResult(
            role_id=RoleId.INVESTMENT, summary="Капітал не оцінено.",
            position="Без бюджету діапазон не обґрунтовується; число не вигадуємо.",
            claims=[c["investment.capital_unknown"]], risks=[r["risk-synthetic-03"]],
            unknowns=["Кошторис і час до milestone"], change_conditions=["Кошторис CRO"],
            section_content=[s[SectionKey.CAPITAL_TO_MILESTONE]]),
    ]


def build_report(version: int) -> Report:
    v2 = version == 2
    pack = build_pack_v2() if v2 else build_pack_v1()
    claims = _claims_v2() if v2 else _claims_v1()
    risks = _risks(v2)
    questions = _questions(v2)
    rec = Recommendation.DO_NOT_INVEST if v2 else Recommendation.CONDITIONAL
    sections = _sections(_SUMMARIES_V2 if v2 else _SUMMARIES_V1, rec, risks, questions, pack.sources)
    revision = None
    if v2:
        before = next(c for c in _claims_v1() if c.id == "translation.safe_exposure")
        after = next(c for c in claims if c.id == "translation.safe_exposure")
        revision = Revision(
            parent_report_id=REPORT_V1_ID, new_evidence_ids=["ev-synthetic-07"],
            changed_claims=[ClaimChange(claim_id="translation.safe_exposure", before=before,
                                        after=after)],
            previous_recommendation=Recommendation.CONDITIONAL,
            new_recommendation=Recommendation.DO_NOT_INVEST,
            explanation=("Нове свідчення ev-synthetic-07 показує серйозну небажану подію при "
                         "потрібній експозиції: claim translation.safe_exposure змінено з unknown "
                         "на contradicted, а рекомендацію — з Conditional на Do Not Invest."))
    return Report(
        id=REPORT_V2_ID if v2 else REPORT_V1_ID, case_id=CASE_ID,
        run_id="run-synthetic-v2" if v2 else "run-synthetic-v1", version=version,
        scope=Scope.PROGRAM, synthetic=True, snapshot_id=pack.snapshot_id, recommendation=rec,
        rationale=("Нове синтетичне свідчення безпеки спростовує ключову умову тези; "
                   "рішення — Do Not Invest." if v2 else
                   "Механізм має часткове обґрунтування, але безпечна експозиція в людини не "
                   "встановлена, а дані програми неповні. Рішення Conditional: інтерес залежить "
                   "від підтвердження безпеки."),
        decision_conditions=(["Повернутися до розгляду лише за незалежних даних про безпечний режим"]
                             if v2 else
                             ["Отримати дані безпеки та експозиції у людини",
                              "Підтвердити біомаркер дії на мішень",
                              "Отримати кошторис і план дослідження фази 1"]),
        sections=sections, roles=_roles(claims, risks, sections, v2), claims=claims,
        evidence=pack.evidence, sources=pack.sources,
        disagreements=[Disagreement(
            topic="Достатність генетичних даних",
            role_ids=[RoleId.SCIENCE, RoleId.TRANSLATION],
            summary="Науковий аналіз бачить підтримку мішені; аналіз перенесення на людину — "
                    "розрив у ланцюзі експозиції.",
            resolution="Голова розглядає генетику як підтримку механізму, а не доказ користі.")],
        risks=risks, diligence_questions=questions, revision=revision)


def build_r5_role_report() -> Report:
    """Display-only fixture for all agreed roles; no expert nodes are executed."""
    report = build_report(1)
    report.id = "rep-synthetic-r5"
    report.run_id = "run-synthetic-r5"
    examples = [
        (RoleId.FAILURE_MINER, "Safe human exposure remains an unresolved failure mode.",
         "translation.safe_exposure", SectionKey.KEY_RISKS),
        (RoleId.INVESTMENT_THRESHOLD, "Safe exposure is required before the thesis can advance.",
         "translation.safe_exposure", SectionKey.CRITICAL_UNKNOWNS),
        (RoleId.PARTNERSHIPS, "No partner interest is established in this fictional case.",
         "partnerships.interest_unknown", SectionKey.COMMERCIAL_OPPORTUNITY),
        (RoleId.IP_LICENSING, "Patent ownership and licensing rights have not been established.",
         "ip_licensing.rights_unknown", SectionKey.KEY_RISKS),
        (RoleId.CHAIR, "The fictional committee remains Conditional pending safe exposure.",
         "translation.safe_exposure", SectionKey.RECOMMENDATION),
        (RoleId.AUDIT, "Evidence links in this display fixture do not establish live audit quality.",
         "translation.safe_exposure", SectionKey.SOURCES),
    ]
    for role_id, summary, claim_id, section_key in examples:
        claim = next((c for c in report.claims if c.id == claim_id), None)
        if claim is None:
            claim = Claim(id=claim_id, text=summary, provenance=Provenance.AI,
                          support_status=SupportStatus.UNKNOWN, scope=report.scope,
                          importance=Importance.MAJOR)
            report.claims.append(claim)
        report.roles.append(RoleResult(
            role_id=role_id, summary=f"Synthetic display example: {summary}",
            position="Illustrative only; missing evidence remains unknown.",
            claims=[claim], risks=[report.risks[0]] if role_id == RoleId.FAILURE_MINER else [],
            unknowns=[summary],
            change_conditions=["Obtain and audit the missing evidence before changing this position."],
            section_content=[SectionContent(
                key=section_key, summary=summary, claim_ids=[claim_id],
                limitations=["Synthetic display fixture; no live analysis was performed."],
            )],
        ))
    integrity.assert_report(report)
    return report


def build_runs() -> tuple[Run, Run]:
    running = Run(id="run-synthetic-running", case_id=CASE_ID, status=RunStatus.RUNNING,
                  stage=RunStage.ANALYZE, report_version=None, warnings=[],
                  trace_id="trace-synthetic-running", mode=RunMode.LIVE,
                  model_version="synthetic", config_version="synthetic-v1")
    failed = Run(id="run-synthetic-failed", case_id=CASE_ID, status=RunStatus.FAILED,
                 stage=RunStage.AUDIT, report_version=None,
                 warnings=["Синтетичний приклад збою"],
                 error=ErrorBody(code="run_interrupted",
                                 message="Run перервано перезапуском сервера; запустіть повторно.",
                                 retryable=True),
                 trace_id="trace-synthetic-failed", mode=RunMode.LIVE,
                 model_version="synthetic", config_version="synthetic-v1")
    return running, failed


def build_all() -> dict[str, BaseModel]:
    """File stem -> model. Validates every object and every integrity rule."""
    pack = build_pack_v1()
    v1, v2 = build_report(1), build_report(2)
    integrity.assert_pack(pack)
    integrity.assert_pack(build_pack_v2())
    integrity.assert_report(v1)
    integrity.assert_report(v2, parent=v1)
    running, failed = build_runs()
    return {"case": build_case(), "evidence-pack": pack, "report-v1": v1, "report-v2": v2,
            "report-r5": build_r5_role_report(),
            "run-running": running, "run-failed": failed}
