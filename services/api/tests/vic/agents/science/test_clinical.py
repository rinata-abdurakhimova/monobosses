import asyncio

import sys
import os

# Вказуємо Python абсолютний шлях до папки src
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "../../../../src")
sys.path.insert(0, os.path.abspath(src_path))

from pydantic import BaseModel, Field
from typing import Any, List, Optional

# ==========================================
# 1. ТИМЧАСОВІ КОНТРАКТИ (замість vic.contracts)
# ==========================================
class CaseInput(BaseModel):
    indication: str
    mechanism: str
    modality: str = "small molecule"
    development_stage: str = "preclinical"
    scope: str = "approach"
    program_data: str = ""

class Source(BaseModel):
    id: str
    title: str
    type: str = "publication"
    published_at: str = "2026-10-01"
    synthetic: bool = False

class Evidence(BaseModel):
    id: str
    source_id: str
    excerpt: str
    locator: str = ""
    scope: str = "approach"
    limitations: str = ""

class EvidencePack(BaseModel):
    sources: list[Source] = []
    evidence: list[Evidence] = []
    retrieval_warnings: list[str] = []

class Claim(BaseModel):
    id: str
    text: str
    provenance: str
    support_status: str
    evidence_ids: list[str]
    assumptions: list[str]
    scope: str
    importance: str

class Risk(BaseModel):
    id: str
    description: str
    priority: str
    claim_ids: list[str]
    impact: str
    next_check: str

class SectionContent(BaseModel):
    key: str
    summary: str
    claim_ids: list[str]
    limitations: list[str]
    structured_data: dict

class RoleResult(BaseModel):
    role_id: str
    summary: str
    position: str
    claims: list[Claim]
    risks: list[Risk]
    unknowns: list[str]
    change_conditions: list[str]
    section_content: SectionContent

# ==========================================
# 2. ІМІТАЦІЯ LLM АДАПТЕРА
# ==========================================
class MockModelAdapter:
    async def generate_structured(self, prompt_id: str, payload: dict, response_model: Any, ctx: Any):
        print(f"\n🚀 [LLM Adapter] Викликано промпт: {prompt_id}")
        print(f"📦 Payload містить ключів: {len(payload)}")
        
        # Базові поля, які є у відповідях всіх трьох агентів
        mock_data = {
            "thesis": "Тестова теза",
            "position": "moderate",
            "unknowns": [],
            "change_conditions": [],
            "limitations": []
        }
        
        # Специфічні поля для кожного агента
        if prompt_id == "science":
            mock_data.update({
                "claims": [],
                "risks": [],
                "supporting_arguments": ["Аргумент за"],
                "opposing_arguments": ["Аргумент проти"]
            })

        elif prompt_id == "translation":
            mock_data.update({
                "links": [],
                "additional_claims": [],
                "barriers": ["Тестовий бар'єр"],
                "data_needed": ["Тестові дані"],
                "risks": []
            })

        elif prompt_id == "clinical":
            class MockTrialSize:
                has_basis = False
                estimate = None
                assumptions = []
                statistical_design_gap = None
                evidence_ids = []
            
            mock_data.update({
                "target_population": "Тестова популяція",
                "clinically_meaningful_outcome": "Тестовий результат",
                "primary_endpoint": "Тестова кінцева точка",
                "secondary_endpoints": [],
                "comparator": "Плацебо",
                "biomarker_strategy": "Тестова стратегія",
                "trial_size": MockTrialSize(),
                "study_sequence": [],
                "regulatory_context": "Тестовий контекст",
                "historical_analogues": [],
                "next_milestone": "Тестовий етап",
                "standard_of_care": "Стандартна терапія",
                "unmet_need": "Тестова медична потреба",
                "claims": [],
                "risks": [],
                "diligence_questions": [],
                "science_gaps_carried_forward": []
            })

        return response_model.model_construct(**mock_data)

class RunContext:
    def __init__(self):
        self.model = MockModelAdapter()

# ==========================================
# 3. ТЕСТОВИЙ ЗАПУСК ТВОЇХ ФУНКЦІЙ
# ==========================================
# Тут ми імпортуємо твої реальні функції (шляхи мають збігатися з твоєю структурою папок)
import sys
import os
# Додаємо шлях до папки services/api/src, щоб імпорти працювали
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "services/api/src")))

# Щоб імпорти from vic.contracts працювали, підміняємо модуль нашими заглушками
import sys
import types
mock_contracts = types.ModuleType("vic.contracts")
mock_contracts.CaseInput = CaseInput
mock_contracts.Source = Source
mock_contracts.Evidence = Evidence
mock_contracts.EvidencePack = EvidencePack
mock_contracts.Claim = Claim
mock_contracts.Risk = Risk
mock_contracts.RoleResult = RoleResult
mock_contracts.SectionContent = SectionContent
mock_contracts.RunContext = RunContext
sys.modules["vic.contracts"] = mock_contracts

from vic.agents.science.scientific import analyze_science
from vic.agents.science.translation import analyze_translation
from vic.agents.science.clinical import analyze_clinical

async def main():
    print("=== ПОЧАТОК ТЕСТУВАННЯ R4 ===")
    
    # Створюємо фейкові вхідні дані
    case = CaseInput(indication="Asthma", mechanism="IL-4 inhibition")
    source = Source(id="src-1", title="Test Paper")
    evidence = Evidence(id="ev-1", source_id="src-1", excerpt="Test excerpt")
    pack = EvidencePack(sources=[source], evidence=[evidence])
    ctx = RunContext()

    # 1. Тест Scientific Agent
    print("\n--- 1. Scientific Agent ---")
    sci_result = await analyze_science(case, pack, ctx)
    print(f"✅ Scientific Analysis пройшов! Role ID: {sci_result.role_id}")

    # 2. Тест Translation Agent
    print("\n--- 2. Translation Agent ---")
    trans_result = await analyze_translation(case, pack, ctx)
    print(f"✅ Translation Analysis пройшов! Role ID: {trans_result.role_id}")

    # 3. Тест Clinical Agent
    print("\n--- 3. Clinical Agent ---")
    clin_result = await analyze_clinical(case, pack, sci_result, trans_result, ctx)
    print(f"✅ Clinical Analysis пройшов! Role ID: {clin_result.role_id}")
    
    print("\n=== ВСІ ТЕСТИ УСПІШНІ! 🎉 ===")

if __name__ == "__main__":
    asyncio.run(main())