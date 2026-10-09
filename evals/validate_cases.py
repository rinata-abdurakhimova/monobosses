"""Offline R5 content checks: no provider, secrets, retrieval or model calls.

PYTHONPATH=services/api/src python evals/validate_cases.py --output /tmp/r5-validation.json
This is dataset validation and direct arithmetic, not LLM-quality scoring.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
from vic.agents.business.calculations import MarketScenario, estimate_market_scenarios
from vic.agents.business.investment_calculations import (
    InvestmentScenario, StressScenario, calculate_investment_scenarios,
)
from vic.agents.business.market import prepare_market_inputs
from vic.config import Settings
from vic.contracts import CaseInput, Run, RunContext, RunMode, RunStatus
from vic.evidence.importer import build_pack, parse_json, verify_pack
from vic.integrity import assert_pack
from vic.modules import Modules
from vic.pipeline import Pipeline
from vic.storage import SqliteRepository

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROLES = {'market', 'investment', 'failure_miner', 'chair',
         'investment_threshold', 'partnerships', 'ip_licensing'}
FROZEN_TIME = datetime(2026, 10, 9, tzinfo=timezone.utc)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_file(value, root):
    require(isinstance(value, str), 'Dataset uses file paths, not inline evaluator labels')
    path = (root / value).resolve()
    require(path.is_relative_to(root.parent.resolve()), f'Path escapes evals: {value}')
    return json.loads(path.read_text(encoding='utf-8'))


def at(value, path):
    for key in path.split('.'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def equals(actual, expected):
    if isinstance(actual, str) and isinstance(expected, str):
        try:
            return Decimal(actual) == Decimal(expected)
        except Exception:
            return actual == expected
    return actual == expected


def numeric_probe(probe):
    """Call the existing deterministic functions, not a scripted LLM response."""
    error = None
    try:
        if probe['engine'] == 'market':
            output = estimate_market_scenarios([MarketScenario.model_validate(s) for s in probe['input']])
        elif probe['engine'] == 'investment':
            inputs = probe['input']
            output = calculate_investment_scenarios(
                [InvestmentScenario.model_validate(s) for s in inputs['scenarios']],
                [StressScenario.model_validate(s) for s in inputs.get('stresses', [])])
        else:
            raise ValueError('Unknown numeric engine')
    except (ValueError, ValidationError) as exc:
        error = str(exc)
    if probe.get('expected_error_contains'):
        require(error is not None and probe['expected_error_contains'] in error,
                f"{probe['id']}: expected rejection {probe['expected_error_contains']!r}, got {error!r}")
        return {'id': probe['id'], 'status': 'passed', 'kind': 'expected_input_rejection'}
    require(error is None, f"{probe['id']}: unexpected input rejection {error}")
    for path, expected in probe['expected_values'].items():
        actual = at(output, path)
        require(equals(actual, expected), f"{probe['id']} {path}: {actual!r} != {expected!r}")
    return {'id': probe['id'], 'status': 'passed', 'kind': 'exact_arithmetic',
            'checked_values': len(probe['expected_values'])}


def current_runner():
    spec = importlib.util.spec_from_file_location('r5_current_evaluation_runner', HERE / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dataset(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = current_runner().validate_manifest(manifest)
    rubric = (HERE / 'rubric.md').read_text(encoding='utf-8')
    rubric_ids = set(re.findall(r'^- \[ \] ([A-Z]\d{2}) —', rubric, re.M))
    cases = []
    for row in rows:
        raw = read_file(row['input'], root)
        pack_raw = read_file(row['pack'], root)
        expected = read_file(row['expectations'], root)
        require(row['type'] == 'synthetic', f"{row['id']}: synthetic only")
        require(expected['case_id'] == row['id'], f"{row['id']}: wrong expectations")
        case = CaseInput.model_validate(raw)
        require(row['as_of_date'] == case.as_of_date.isoformat(), f"{row['id']}: date mismatch")
        docs = [parse_json(d) for d in pack_raw['documents']]
        require(all(d.synthetic for d in docs), f"{row['id']}: unlabelled synthetic document")
        imported = build_pack(docs, retrieved_at=FROZEN_TIME)
        assert_pack(imported.pack)
        require(not verify_pack(imported), f"{row['id']}: broken excerpt/locator")
        ev = {e.id: e for e in imported.pack.evidence}
        sources = {s.id: s for s in imported.pack.sources}
        require(set(expected['role_expectations']) == ROLES, f"{row['id']}: missing role expectations")
        require(set(row['target_roles']) == ROLES, f"{row['id']}: missing role targets")
        require(set(expected['focus_roles']) <= ROLES, f"{row['id']}: invalid focus role")
        require(set(expected['rubric_ids']) <= rubric_ids, f"{row['id']}: unknown rubric ID")
        require(not set(expected['rubric_ids']) & set(expected['rubric_na']), f"{row['id']}: active and N/A overlap")
        require(set(expected['rubric_na']) <= rubric_ids, f"{row['id']}: unknown N/A ID")
        require(expected['label_status'] == 'author_defined_pending_R3_R4_R5_review', 'No fabricated expert labels')
        require(expected['allowed_recommendations'] == row['allowed_recommendations'], 'Recommendation metadata mismatch')
        require(bool(expected['allowed_recommendations']) and set(expected['allowed_recommendations']) <= {'Invest', 'Conditional', 'Do Not Invest'}, 'Invalid allowed recommendation')
        require(bool(expected['required_facts']) and bool(expected['required_unknowns']) and bool(expected['forbidden_assertions']), 'Incomplete semantic expectations')
        fact_ids = [f['id'] for f in expected['required_facts']]
        require(len(fact_ids) == len(set(fact_ids)), 'Duplicate expected fact IDs')
        excluded = set(expected.get('excluded_documents', []))
        for key, mapping in expected['document_map'].items():
            require(mapping['source_id'] in sources, f"{row['id']}: unknown mapped source")
            require(bool(mapping['evidence_ids']), 'Empty mapped evidence')
            for eid in mapping['evidence_ids']:
                require(eid in ev and ev[eid].source_id == mapping['source_id'], 'Wrong document/evidence link')
            publication = sources[mapping['source_id']].published_at
            if publication is None or publication > case.as_of_date:
                require(key in excluded, 'Unavailable document is not marked excluded')
        require(excluded <= set(expected['document_map']), 'Unknown excluded document')
        for f in expected['required_facts']:
            require(f['document'] not in excluded, 'Expected required fact depends on unavailable evidence')
            require(f['source_id'] == expected['document_map'][f['document']]['source_id'], 'Fact source mismatch')
            require(set(f['evidence_ids']) == set(expected['document_map'][f['document']]['evidence_ids']), 'Fact evidence mismatch')
        for role, rules in expected['role_expectations'].items():
            require(bool(rules) and all(r['requirement'].strip() for r in rules), f'Missing requirements for {role}')
            facts = {f['id']: f for f in expected['required_facts']}
            for rule in rules:
                if 'premise_fact_ids' in rule:
                    premises = rule['premise_fact_ids']
                    require(bool(premises) and set(premises) <= facts.keys(), 'Unknown inference premise fact')
                    premise_evidence = {eid for fid in premises for eid in facts[fid]['evidence_ids']}
                    require(set(rule.get('evidence_ids', [])) == premise_evidence,
                            'Inference must cite all premise evidence')
                elif 'evidence_ids' in rule:
                    require(set(rule['evidence_ids']) <= ev.keys(), 'Unknown role expectation evidence')
        marker = expected['evaluator_only_marker']
        runtime = json.dumps({'input': raw, 'pack': pack_raw}, ensure_ascii=False)
        require(marker not in runtime, 'Evaluator marker leaked into runtime input')
        require(not any(key in raw or key in pack_raw for key in ('expectations', 'allowed_recommendations', 'role_expectations', 'identity_mapping')), 'Labels in runtime files')
        payload = prepare_market_inputs(case, imported.pack, None)
        require(marker not in json.dumps(payload, ensure_ascii=False, default=str), 'Expectations leaked into Market payload')
        require(row['leakage']['overall'] == 'partial' and not row['leakage']['blind_guess']['performed'], 'Unsupported leakage guarantee')
        cases.append({'row': row, 'case': case, 'imported': imported, 'expected': expected,
                      'market_payload_chars': len(json.dumps(payload, ensure_ascii=False, default=str, separators=(',', ':')))})
    by_id = {c['row']['id']: c for c in cases}
    # The current runner stores uploads cumulatively: require linear family revisions.
    last = {}
    for c in cases:
        row, expected = c['row'], c['expected']
        if row.get('parent'):
            parent = by_id[row['parent']]
            require(parent['row']['family'] == row['family'], 'Cross-family parent')
            require(parent['case'] == c['case'], 'Revision input changed')
            require(last.get(row['family']) == row['parent'], 'Branching revisions contaminate cumulative imports')
            old_docs = {d.content_hash: d for d in parent['imported'].documents}
            new_docs = {d.content_hash: d for d in c['imported'].documents}
            require(set(old_docs) < set(new_docs), 'Revision must append evidence without dropping parent documents')
            for key, value in old_docs.items():
                require(value == new_docs[key], 'Parent document provenance modified')
            revision = expected['revision']
            require(revision['parent'] == row['parent'], 'Expected parent mismatch')
            old_map, new_map = parent['expected']['document_map'], expected['document_map']
            require(set(new_map) - set(old_map) == set(revision['new_document_keys']), 'Unexpected change in revision documents')
        else:
            require('revision' not in expected, 'Revision expectations without parent')
        last[row['family']] = row['id']
    return manifest, cases


def no_network(*args, **kwargs):
    raise AssertionError('Offline validator must never call retrieval or a model provider')


async def check_pipeline_retrieval(cases):
    """Exercise actual storage/import/as-of/revision pack assembly, stopping before analysis."""
    statuses, parents = [], {}
    with tempfile.TemporaryDirectory(prefix='r5-case-validation-') as temp:
        repo = SqliteRepository(str(Path(temp) / 'checks.sqlite3'), seed=False)
        settings = Settings(_env_file=None, dev_stubs=False)
        modules = Modules(build_evidence_pack=no_network, origin={'build_evidence_pack': 'offline-real-path'})
        for c in cases:
            row = c['row']
            if row.get('parent'):
                cid, previous = parents[row['parent']]
                parent = SimpleNamespace(sources=previous.sources, evidence=previous.evidence)
            else:
                cid = repo.create_case(c['case'])
                parent = None
            repo.add_import(cid, c['imported'])
            pipeline = Pipeline(repo, settings, lambda: modules, no_network)
            pipeline.run = Run(id='run-'+row['id'], case_id=cid, status=RunStatus.QUEUED,
                               trace_id='trace-'+row['id'], mode=RunMode.EVIDENCE_ONLY)
            pipeline.ctx = RunContext(case_id=cid, run_id=pipeline.run.id, snapshot_id=None, as_of_date=c['case'].as_of_date,
                                      mode=RunMode.EVIDENCE_ONLY)
            pack = await pipeline._retrieve(c['case'], parent, modules)
            assert_pack(pack)
            expected = c['expected']
            excluded = set(expected.get('excluded_documents', []))
            wanted = {eid for key, m in expected['document_map'].items() if key not in excluded for eid in m['evidence_ids']}
            require({e.id for e in pack.evidence} == wanted, f"{row['id']}: actual effective evidence set differs")
            if parent:
                old = {e.id: e for e in previous.evidence}
                new = {e.id: e for e in pack.evidence}
                require(all(new[k] == v for k, v in old.items()), 'Parent evidence mutated by retrieval')
            effective_payload = prepare_market_inputs(c['case'], pack, None)
            require(expected['evaluator_only_marker'] not in json.dumps(effective_payload, default=str), 'Labels entered effective node input')
            parents[row['id']] = (cid, pack)
            statuses.append({'id': row['id'], 'status': 'passed', 'split': row['split'],
                             'sources': len(pack.sources), 'evidence_items': len(pack.evidence),
                             'market_payload_chars': len(json.dumps(effective_payload, ensure_ascii=False, default=str, separators=(',', ':'))),
                             'excluded_documents': len(excluded), 'scope': 'import/retrieval/input only; no model analysis'})
    return statuses


def check_lock(manifest_path):
    lock_path = Path(manifest_path).parent / 'dataset-lock.json'
    if not lock_path.exists():
        return 'not_created'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    for path, digest in lock['files'].items():
        require(hashlib.sha256((HERE / path).read_bytes()).hexdigest() == digest, f'Dataset changed since lock: {path}')
    for path, digest in lock['code_baseline']['files'].items():
        require(hashlib.sha256((REPO / path).read_bytes()).hexdigest() == digest, f'Code baseline changed: {path}; re-review/revalidate cases')
    return 'matched'


def validate(manifest_path=HERE / 'cases' / 'manifest.json'):
    manifest_path = Path(manifest_path).resolve()
    manifest, cases = load_dataset(manifest_path)
    dataset_result = asyncio.run(check_pipeline_retrieval(cases))
    probe_results = []
    by_id = {c['row']['id']: c for c in cases}
    for file in manifest.get('numeric_probes', []):
        probe = read_file(file, manifest_path.parent)
        require(probe['case_id'] in by_id, 'Numeric probe references missing case')
        probe_results.append(numeric_probe(probe))
    return {'validation_type': 'offline_content_and_deterministic_arithmetic',
            'dataset_version': manifest['dataset_version'],
            'model_calls': 0, 'live_quality_evaluated': False, 'expert_labels_provided': False,
            'cases_checked': len(cases), 'families': len({c['row']['family'] for c in cases}),
            'splits': dict(Counter(c['row']['split'] for c in cases)),
            'target_roles': sorted(ROLES), 'paired_revisions': sum(bool(c['row'].get('parent')) for c in cases),
            'case_checks': dataset_result, 'numeric_probes': probe_results,
            'numeric_values_checked': sum(p.get('checked_values', 0) for p in probe_results),
            'dataset_lock': check_lock(manifest_path),
            'limitations': ['No full pipeline analysis or real LLM-quality results.',
              'Market payload character counts exclude prompt, schema, clinical context and retries; these are not token counts or gateway-fit guarantees.',
              'Authored expectations await R3/R4/R5 review; holdout has not been used for tuning.',
              'Direct numeric probes are caller-reviewed fixtures; the integrated runner does not pass MarketScenario arguments.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=HERE / 'cases' / 'manifest.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = validate(args.manifest)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Cases: {result['cases_checked']}; splits: {result['splits']}; numeric probes: {len(result['numeric_probes'])}; model calls: 0")
    print('Passed: schema, excerpt provenance, family/revision separation, real offline retrieval and deterministic expectations.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
