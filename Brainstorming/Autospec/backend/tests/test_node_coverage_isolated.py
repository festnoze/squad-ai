"""Source-bound frontend coverage; never execute npm or generated tests on host."""
import copy
import json
import os
from types import SimpleNamespace

import pytest

from autospec.orchestrator import isolated_validation as module
from autospec.orchestrator.isolated_validation import IsolatedValidator, _istanbul_coverage, _admit_source_coverage


def _report():
    return {'/tmp/product/src/business.js': {
        'statementMap': {'0': {'start': {'line': 1}, 'end': {'line': 1}}}, 's': {'0': 1},
        'branchMap': {'0': {'locations': [
            {'start': {'line': 1}, 'end': {'line': 1}}, {'start': {'line': 1}, 'end': {'line': 1}}]}},
        'b': {'0': [1, 0]}}}


def test_istanbul_totals_are_source_only_and_missing_files_fail_closed():
    inventory = {'src/business.js': 'hash', 'src/untouched.js': 'hash2'}
    report = _report()
    report['/tmp/product/src/untouched.js'] = {'statementMap': {'0': {'start': {'line': 1}}},
        's': {'0': 0}, 'branchMap': {}, 'b': {}}
    report['/tmp/product/tests/test.js'] = copy.deepcopy(report['/tmp/product/src/business.js'])
    normalized = _istanbul_coverage(report, inventory, {name: 1 for name in inventory})
    result = _admit_source_coverage(normalized, inventory, 'src', 'source', SimpleNamespace(fingerprint='env', image='image'))
    assert set(result['files']) == set(inventory)
    assert result['totals'] == {'covered_lines': 1, 'num_statements': 2, 'missing_lines': 1,
        'num_branches': 2, 'covered_branches': 1, 'percent_covered': 50}
    assert result['autospec_inventory']['source_fingerprint'] == 'source'
    del normalized['files']['src/untouched.js']
    with pytest.raises(ValueError, match='omitted'):
        _admit_source_coverage(normalized, inventory, 'src', 'source', SimpleNamespace(fingerprint='env', image='image'))


@pytest.mark.parametrize('defect', ['negative', 'bool', 'line', 'maps', 'arms', 'branchline'])
def test_istanbul_invalid_maps_and_counts_are_not_evidence(defect):
    report = _report()
    value = report['/tmp/product/src/business.js']
    if defect == 'negative': value['s']['0'] = -1
    if defect == 'bool': value['b']['0'][0] = True
    if defect == 'line': value['statementMap']['0']['start']['line'] = 2
    if defect == 'maps': value['branchMap'] = {}
    if defect == 'arms': value['b']['0'] = [1]
    if defect == 'branchline': value['branchMap']['0']['locations'][0]['end']['line'] = 2
    with pytest.raises(ValueError):
        _istanbul_coverage(report, {'src/business.js': 'hash'}, {'src/business.js': 1})


@pytest.mark.parametrize('coverage_version', [None, '3.0.0'])
def test_node_coverage_provider_must_be_explicit_exact_locked(tmp_path, monkeypatch, coverage_version):
    root = tmp_path / 'product'; root.mkdir(); (root/'src').mkdir()
    (root/'src/business.js').write_text('export const value=1;\n')
    dependencies = {'vitest': '2.1.9'}
    packages = {'node_modules/vitest': {'version': '2.1.9'}}
    if coverage_version:
        dependencies['@vitest/coverage-v8'] = coverage_version
        packages['node_modules/@vitest/coverage-v8'] = {'version': coverage_version}
    (root/'package.json').write_text(json.dumps({'devDependencies': dependencies}))
    (root/'package-lock.json').write_text(json.dumps({'packages': packages}))
    manager = SimpleNamespace(prepare=lambda *_: SimpleNamespace(fingerprint='env', image='image'))
    monkeypatch.setattr(module, 'run_isolated', lambda *a, **k: pytest.fail('unqualified provider must not execute'))
    with pytest.raises(RuntimeError, match='locked vitest'):
        IsolatedValidator(tmp_path/'cache', manager=manager).run_suite(root, 'node', 'test',
            tmp_path/'report.json', coveragepath=tmp_path/'coverage.json', coverage_source='src')


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION') != '1', reason='Opt-in real locked Vitest V8 Linux coverage')
def test_real_node_coverage_includes_untouched_despite_product_config(tmp_path):
    root = tmp_path/'product'; root.mkdir(); (root/'src').mkdir(); (root/'tests').mkdir()
    (root/'package.json').write_text(json.dumps({'name': 'coverage-proof', 'version': '1.0.0', 'type': 'module',
        'devDependencies': {'vitest': '2.1.9', '@vitest/coverage-v8': '2.1.9'}}))
    (root/'src/business.js').write_text('export function choose(value) {\n if (value) return 1;\n return 0;\n}\n')
    (root/'src/untouched.js').write_text('export function untouched(value) {\n if (value) return 10;\n return 20;\n}\n')
    (root/'tests/business.test.js').write_text("import {test,expect} from 'vitest';\nimport {choose} from '../src/business.js';\ntest('true and false',()=>{expect(choose(true)).toBe(1);expect(choose(false)).toBe(0)});\n")
    (root/'vitest.config.mjs').write_text("export default {test:{coverage:{all:false,include:['src/business.js'],exclude:['src/untouched.js']}}};\n")
    # A producer's cached JSON can neither replace the fresh tmpfs report nor
    # inflate coverage totals with tests/configuration files.
    (root/'suite-coverage.json').write_text('{"totals":{"percent_covered":100}}')
    validator = IsolatedValidator(tmp_path/'cache', timeout=600)
    validator.manager.ensure_lock(root, 'node')
    result = validator.run_suite(root, 'node', 'test', tmp_path/'suite.json',
        coveragepath=tmp_path/'coverage.json', coverage_source='src')
    assert result.evidence.exit_code == 0 and result.evidence.report_valid, result.output
    assert result.evidence.collected == 1 and list(result.evidence.outcomes.values()) == ['passed']
    coverage = result.coverage
    assert coverage is not None and json.loads((tmp_path/'coverage.json').read_text()) == coverage
    assert set(coverage['files']) == {'src/business.js', 'src/untouched.js'}
    assert coverage['files']['src/business.js']['summary']['covered_lines'] > 0
    assert coverage['files']['src/untouched.js']['summary']['covered_lines'] == 0
    assert coverage['files']['src/untouched.js']['summary']['missing_lines'] > 0
    assert coverage['totals']['percent_covered'] < 100
    assert coverage['autospec_inventory']['source_fingerprint'] == result.source_fingerprint
    assert coverage['autospec_inventory']['environment_fingerprint'] == result.fingerprint
    assert set(coverage['autospec_inventory']['files']) == set(coverage['files'])
    assert (root/'suite-coverage.json').read_text() == '{"totals":{"percent_covered":100}}'
    assert not (root/'node_modules').exists()
