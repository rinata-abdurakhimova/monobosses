"""Meaningful checks for dataset corruption, label leakage and incorrect denominators/inputs."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r5_dataset_validator', HERE / 'validate_cases.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


@pytest.fixture
def copy_dataset(tmp_path):
    target = tmp_path / 'evals'
    shutil.copytree(HERE / 'cases', target / 'cases')
    return target


def edit_json(path, edit):
    data = json.loads(path.read_text(encoding='utf-8'))
    edit(data)
    path.write_text(json.dumps(data), encoding='utf-8')


def test_all_cases_use_real_offline_import_and_retrieval():
    result = validator.validate()
    assert result['cases_checked'] == 21
    assert result['splits'] == {'development': 13, 'holdout': 8}
    assert result['families'] == 18
    assert result['paired_revisions'] == 3
    assert result['model_calls'] == 0 and not result['live_quality_evaluated']
    assert len(result['numeric_probes']) == 8
    assert sum(p['kind'] == 'expected_input_rejection' for p in result['numeric_probes']) == 3
    assert all(c['status'] == 'passed' for c in result['case_checks'])
    temporal = next(c for c in result['case_checks'] if c['id'] == 'hold-06-discontinued-unknown')
    assert temporal['excluded_documents'] == 1 and temporal['sources'] == 1


def test_each_split_is_accepted_by_current_runner():
    for split, count in [('development', 13), ('holdout', 8)]:
        _, cases = validator.load_dataset(HERE / 'cases' / f'manifest.{split}.json')
        assert len(cases) == count


def test_rejects_label_marker_in_runtime_input(copy_dataset):
    case = copy_dataset / 'cases/dev-01-sparse'
    label = json.loads((case / 'expectations.json').read_text(encoding='utf-8'))['evaluator_only_marker']
    edit_json(case / 'input.json', lambda d: d.update(program_data=label))
    with pytest.raises(ValueError, match='marker leaked'):
        validator.load_dataset(copy_dataset / 'cases/manifest.json')


def test_rejects_unknown_expected_source(copy_dataset):
    path = copy_dataset / 'cases/dev-01-sparse/expectations.json'
    edit_json(path, lambda d: d['document_map']['sparse-description'].update(source_id='src-not-in-pack'))
    with pytest.raises(ValueError, match='unknown mapped source'):
        validator.load_dataset(copy_dataset / 'cases/manifest.json')


def test_rejects_family_across_splits(copy_dataset):
    path = copy_dataset / 'cases/manifest.json'
    edit_json(path, lambda d: d['cases'][10].update(split='holdout'))
    with pytest.raises(ValueError, match='same split'):
        validator.load_dataset(path)


def test_rejects_branching_revision_contamination(copy_dataset):
    path = copy_dataset / 'cases/manifest.json'
    edit_json(path, lambda d: d['cases'][11].update(parent='dev-10-safety-before'))
    with pytest.raises(ValueError, match='Branching revisions'):
        validator.load_dataset(path)


def test_rejects_excerpt_not_in_document(copy_dataset):
    path = copy_dataset / 'cases/dev-01-sparse/pack.json'
    edit_json(path, lambda d: d['documents'][0]['evidence'][0].update(excerpt='A result that never occurred in the source.'))
    with pytest.raises(Exception, match='not in the document'):
        validator.load_dataset(copy_dataset / 'cases/manifest.json')


def test_rejects_required_fact_from_future_source(copy_dataset):
    path = copy_dataset / 'cases/hold-06-discontinued-unknown/expectations.json'
    def future_fact(d):
        m = d['document_map']['future-outcome']
        d['required_facts'].append({'id': 'future-fact', 'document': 'future-outcome',
                                  'assertion': 'toxicity', 'importance': 'critical', **m})
    edit_json(path, future_fact)
    with pytest.raises(ValueError, match='unavailable evidence'):
        validator.load_dataset(copy_dataset / 'cases/manifest.json')


def test_missing_price_cannot_pass_as_zero():
    probe = json.loads((HERE / 'numeric/market-missing-price.json').read_text(encoding='utf-8'))
    probe['expected_values']['0.annual_market_opportunity'] = '0'
    with pytest.raises(ValueError, match='None.*0'):
        validator.numeric_probe(probe)


def test_partial_budget_cannot_pass_as_full_capital():
    probe = json.loads((HERE / 'numeric/investment-partial.json').read_text(encoding='utf-8'))
    probe['expected_values']['scenarios.0.capital_to_milestone'] = {'minimum': '40000', 'maximum': '40000'}
    with pytest.raises(ValueError, match='capital_to_milestone'):
        validator.numeric_probe(probe)


def test_dataset_lock_detects_modified_file(copy_dataset, monkeypatch):
    monkeypatch.setattr(validator, 'HERE', copy_dataset)
    path = copy_dataset / 'cases/dev-01-sparse/input.json'
    path.write_text(path.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    with pytest.raises(ValueError, match='Dataset changed since lock'):
        validator.check_lock(copy_dataset / 'cases/manifest.json')


@pytest.mark.parametrize('defect', ['missing_protocol', 'unknown_premise'])
def test_rejects_inference_without_both_valid_premises(copy_dataset, defect):
    path = copy_dataset / 'cases/dev-06-role-conflict/expectations.json'
    def corrupt(data):
        rule = data['role_expectations']['market'][-1]
        if defect == 'missing_protocol':
            rule['evidence_ids'] = ['ev-67fc40acbe52-001']
        else:
            rule['premise_fact_ids'] = ['nonexistent-fact']
    edit_json(path, corrupt)
    with pytest.raises(ValueError, match='Inference must cite all premise evidence|Unknown inference premise fact'):
        validator.load_dataset(copy_dataset / 'cases/manifest.json')
