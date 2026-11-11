"""Regression tests for false acceptance; fixtures are rebuilt without local RO-KBs."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glimmer.tools import run as runner

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / 'examples/synthetic-provenance'


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='glimmer tests ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        shutil.copytree(EXAMPLE, self.root, ignore=shutil.ignore_patterns('rokb', 'out', '__pycache__', '*manifest*'))
        self.generate()
        self.rokb = self.root / 'rokb'
        self.graph = runner.load_graph(self.rokb)
        self.mean = 'run-synth-mean'

    def generate(self, *args):
        subprocess.run([sys.executable, str(self.root / 'emit_graph.py'), *args], check=True, capture_output=True)

    def run_node(self, name=None, mode='reproduce', **kwargs):
        return runner.run_node(self.rokb, name or self.mean, mode=mode, offline=True,
                               no_container=kwargs.pop('no_container', True), graph=self.graph, **kwargs)

    def prime_summary(self):
        for name in [self.mean, 'run-synth-mean-fast', 'run-synth-classifier']:
            self.assertIn(self.run_node(name).verdict, runner.SUCCESS)
        self.generate('--pin-summary-inputs')
        self.graph = runner.load_graph(self.rokb)

    def mutate(self, name=None):
        return self.graph[name or self.mean][1]

    def test_clean_fixture_positive_and_negative(self):
        self.prime_summary()
        self.assertEqual(self.run_node('run-synth-agent-summary').verdict, 'structurally-valid')
        self.assertEqual(self.run_node('run-synth-gate-fail').verdict, 'gate-failed')
        self.assertFalse((self.root / 'out/mean_bad.json').exists())

    def test_generator_is_deterministic_without_outputs(self):
        before = {str(p.relative_to(self.rokb)): p.read_bytes() for p in self.rokb.rglob('*') if p.is_file()}
        self.generate()
        after = {str(p.relative_to(self.rokb)): p.read_bytes() for p in self.rokb.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / 'out').exists())

    def test_wrong_input_pin_stops_command(self):
        pin = self.mutate()['inputs'][0]
        pin['datalad-annex-key'] = 'SHA256E-s1--' + '0' * 64
        verdict = self.run_node()
        self.assertEqual(verdict.verdict, 'gate-failed')
        self.assertFalse((self.root / 'out/mean.json').exists())

    def test_missing_pin_is_not_accepted_even_when_planned(self):
        fm = self.mutate(); fm['status'] = 'planned'; fm['inputs'][0].pop('datalad-annex-key')
        self.assertEqual(self.run_node().verdict, 'gate-failed')

    def test_modified_input_is_not_accepted(self):
        path = self.root / 'inputs/signal.json'
        path.write_text(path.read_text().replace('0.5', '0.6') + ' ')
        self.assertEqual(self.run_node().verdict, 'gate-failed')

    def test_offline_missing_input(self):
        (self.root / 'inputs/signal.json').unlink()
        self.assertEqual(self.run_node().verdict, 'inputs-unavailable')

    def test_annex_supported_hash_checks_size_and_bytes(self):
        path = self.root / 'inputs/signal.json'
        data = path.read_bytes()
        pin = {'datalad-annex-key': f'MD5E-s{len(data)}--{hashlib.md5(data).hexdigest()}.json'}
        self.assertTrue(runner._verify_pin(pin, path)[0])
        pin['datalad-annex-key'] = pin['datalad-annex-key'].replace(f's{len(data)}', 's1')
        self.assertFalse(runner._verify_pin(pin, path)[0])
        self.assertFalse(runner._verify_pin({'datalad-annex-key': 'MD5E-local--signal'}, path)[0])

    def test_git_commit_pin_checks_actual_blob(self):
        folder = self.root / 'git-input';folder.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(folder),*args], stderr=subprocess.DEVNULL, text=True).strip()
        git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
        path=folder/'source file.json';path.write_text('{"x": 1}')
        git('add','.');git('commit','-m','fixture');commit=git('rev-parse','HEAD')
        pin={'datalad-commit-sha':commit}
        self.assertTrue(runner._verify_pin(pin,path)[0])
        tree=git('rev-parse','HEAD^{tree}')
        self.assertFalse(runner._verify_pin({'datalad-commit-sha':tree},path)[0])
        path.write_text('{"x": 2}')
        self.assertFalse(runner._verify_pin(pin,path)[0])
        self.assertFalse(runner._verify_pin({'datalad-commit-sha':'HEAD'},path)[0])

    def test_missing_validator_stops_command(self):
        std=self.graph['standard-synth-signal-v1'][1]
        std['validator']['command']='definitely-not-an-installed-validator {path}'
        self.assertEqual(self.run_node().verdict,'gate-failed')
        std.pop('validator')
        self.assertEqual(self.run_node().verdict,'gate-failed')
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_duplicate_input_nodes_fail_before_execution(self):
        fm=self.mutate();fm['inputs'].append(copy.deepcopy(fm['inputs'][0]))
        self.assertEqual(self.run_node().verdict,'gate-failed')
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_json_sidecar_writeback_preserves_format_and_baseline(self):
        path,fm=self.graph[self.mean]
        baseline=copy.deepcopy(fm['outputs'])
        path.write_text(json.dumps(fm))
        verdict=self.run_node()
        self.assertEqual(verdict.verdict,'normalized-match')
        runner.write_verdict_back(self.rokb,self.mean,verdict)
        updated=json.loads(path.read_text())
        self.assertEqual(updated['outputs'],baseline)
        self.assertEqual(updated['replay-verdict']['verdict'],'normalized-match')

    def test_forward_mixed_outputs_check_only_structural_trace(self):
        self.prime_summary()
        fm=self.mutate('run-synth-agent-summary')
        fm['outputs'].append(copy.deepcopy(self.mutate()['outputs'][0]))
        # Execute both existing fixture programs without relying on shell quoting.
        program=self.root/'mixed.py'
        program.write_text('import runpy, sys\n'
                           'sys.argv=["mean", "inputs/signal.json", "out/mean.json"]\n'
                           'runpy.run_path("code/compute_mean.py",run_name="__main__")\n'
                           'sys.argv=["summary", "out/mean.json", "out/acc.json", "out/summary.json"]\n'
                           'runpy.run_path("code/summarize_agent.py",run_name="__main__")\n')
        # The mean is already a pinned summary input; choose a distinct product.
        fm['outputs'][-1]['output-path']='out/extra.json'
        program.write_text(program.read_text().replace('"out/mean.json"]','"out/extra.json"]'))
        fm['command']='python3 mixed.py'
        self.assertEqual(self.run_node('run-synth-agent-summary',mode='run').verdict,'executed')

    def test_unknown_standard_stops_command(self):
        self.mutate()['inputs'][0]['conforms-to']='unknown-standard'
        self.assertEqual(self.run_node().verdict,'gate-failed')

    def test_input_node_conformance_cannot_be_silently_dropped(self):
        self.mutate()['inputs'][0].pop('conforms-to')
        self.graph['standard-synth-signal-v1'][1].pop('validator')
        self.assertEqual(self.run_node().verdict,'gate-failed')
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_required_standard_without_input_binding_fails(self):
        self.mutate()['edges'].append({'type':'requires-standard','target':'unbound-standard'})
        self.assertEqual(self.run_node().verdict,'gate-failed')
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_host_execution_requires_explicit_opt_in(self):
        v=self.run_node(no_container=False)
        self.assertEqual(v.verdict,'error')
        self.assertIn('--no-container',v.notes)
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_declared_container_without_datalad_never_falls_back(self):
        fm=self.mutate();fm['container-image']='fixture';fm['container-digest']='sha256:'+'0'*64
        with patch.object(runner.shutil,'which',return_value=None):
            v=self.run_node(no_container=False)
        self.assertEqual(v.verdict,'error')
        self.assertIn('no host fallback',v.notes)
        self.assertFalse((self.root/'out/mean.json').exists())

    def test_registered_container_argv_and_digest(self):
        image=self.root/'fixture.sif';image.write_bytes(b'container fixture, not executable')
        fm=copy.deepcopy(self.mutate());fm.update({'container-image':'registered-name','container-digest':runner.sha256_file(image),
                                                 'command':'python "script with spaces.py" "a b"'})
        listing=subprocess.CompletedProcess([],0,json.dumps({'name':'registered-name','path':str(image),'status':'ok'})+'\n','')
        execution=subprocess.CompletedProcess([],0,'','')
        with patch.object(runner.shutil,'which',return_value='/fake/datalad'), patch.object(runner.subprocess,'run',side_effect=[listing,execution]) as called:
            rc,via,_=runner.execute(fm,self.root,no_container=False)
        self.assertEqual(rc,0);self.assertIn('SHA-256 checked',via)
        argv=called.call_args_list[1].args[0]
        self.assertEqual(argv[argv.index('-n')+1],'registered-name')
        self.assertEqual(argv[-3:],['python','script with spaces.py','a b'])
        self.assertIn('--input',argv);self.assertIn('--output',argv)
        image.write_bytes(b'tampered')
        with patch.object(runner.shutil,'which',return_value='/fake/datalad'), patch.object(runner.subprocess,'run',return_value=listing) as called:
            rc,_,note=runner.execute(fm,self.root,no_container=False)
        self.assertNotEqual(rc,0);self.assertIn('digest mismatch',note);self.assertEqual(called.call_count,1)

    def test_failed_container_command_never_calls_host(self):
        image=self.root/'fixture.sif';image.write_bytes(b'fixture')
        fm=copy.deepcopy(self.mutate());fm.update({'container-image':'fixture','container-digest':runner.sha256_file(image)})
        listing=subprocess.CompletedProcess([],0,json.dumps({'name':'fixture','path':str(image),'status':'ok'}),'')
        with patch.object(runner.shutil,'which',return_value='/fake/datalad'), patch.object(runner.subprocess,'run',side_effect=[listing,subprocess.CompletedProcess([],1,'','container failed')]) as called:
            rc,_,_=runner.execute(fm,self.root,no_container=False)
        self.assertEqual(rc,1);self.assertEqual(called.call_count,2)

    def test_missing_output_is_not_executed(self):
        self.mutate()['command']='python3 -c "pass"'
        v=self.run_node(mode='run')
        self.assertEqual(v.verdict,'error');self.assertIn('missing',v.notes)

    def test_stale_output_is_not_executed(self):
        self.assertEqual(self.run_node(mode='run').verdict,'executed')
        self.mutate()['command']='python3 -c "pass"'
        v=self.run_node(mode='run')
        self.assertEqual(v.verdict,'error');self.assertIn('not refreshed',v.notes)

    def test_empty_output_set_never_passes(self):
        self.mutate()['outputs']=[]
        self.assertEqual(self.run_node().verdict,'error')

    def test_output_cannot_alias_input(self):
        self.mutate()['outputs'][0]['output-path']='inputs/signal.json'
        before=(self.root/'inputs/signal.json').read_bytes()
        self.assertEqual(self.run_node(mode='run').verdict,'error')
        self.assertEqual(before,(self.root/'inputs/signal.json').read_bytes())

    def test_unknown_mode_or_provenance_fails(self):
        self.assertEqual(self.run_node(mode='typo').verdict,'error')
        self.mutate()['provenance-mode']='typo'
        self.assertEqual(self.run_node().verdict,'error')

    def test_tampered_expected_hash(self):
        self.mutate()['outputs'][0]['expected-hash']='sha256:'+'0'*64
        self.assertEqual(self.run_node().verdict,'mismatch')

    def test_raw_bytes_are_distinct_from_normalized_content(self):
        path=self.root/'dotted.result.json';path.write_text('{"x":1,"y":2}')
        raw=runner.sha256_file(path);normalized=runner.normalized_hash(path)[0]
        path.write_text('{ "y": 2, "x": 1 }')
        pin={'node':'test','output-path':path.name,'expected-hash':raw}
        self.assertFalse(runner.verify_byte_identical(pin,self.root)['passed'])
        pin.update({'tier':'normalized-content','expected-hash':normalized})
        self.assertTrue(runner.verify_byte_identical(pin,self.root)['passed'])
        self.assertEqual(runner.normalized_hash(path)[1],'json-canonical')

    def test_empty_numeric_check_does_not_pass(self):
        self.mutate('run-synth-classifier')['outputs'][0]['expected-values']={}
        self.assertEqual(self.run_node('run-synth-classifier').verdict,'mismatch')

    def test_numeric_invalid_values_and_tolerances_fail(self):
        for observed,expected,tol in [(True,1,{}),(float('nan'),1,{}),(1,float('inf'),{}),
                                      (1,1,{'abs':-1}),(1,1,{'rel':float('inf')}),(1,1,{'abs':True}),
                                      (1,1,{'typo':1}),(1,1,[])]:
            with self.subTest(observed=observed,expected=expected,tol=tol):
                self.assertFalse(runner._tol_pass(observed,expected,tol))
        self.assertTrue(runner._tol_pass(1.001,1,{'abs':0.01}))

    def test_empty_trace_does_not_pass(self):
        self.assertFalse(runner.verify_structural({},self.graph)['passed'])
        self.prime_summary()
        script=self.root/'code/summarize_agent.py';script.write_text(script.read_text().replace("'reasoning-trace': trace", "'reasoning-trace': {}"))
        self.assertEqual(self.run_node('run-synth-agent-summary').verdict,'mismatch')

    def test_false_numeric_claim_in_actual_output_fails(self):
        self.prime_summary()
        script=self.root/'code/summarize_agent.py';script.write_text(script.read_text().replace("'value': mean", "'value': mean + 99"))
        v=self.run_node('run-synth-agent-summary')
        self.assertEqual(v.verdict,'mismatch')
        self.assertFalse(v.structural_checks[0]['checks'][0]['passed'])

    def test_stale_sidecar_trace_cannot_mask_missing_output_trace(self):
        self.prime_summary()
        script=self.root/'code/summarize_agent.py';script.write_text(script.read_text().replace("'reasoning-trace': trace", "'ignored-trace': trace"))
        self.assertEqual(self.run_node('run-synth-agent-summary',mode='run').verdict,'mismatch')

    def test_unpinned_citation_and_unverifiable_retriever_fail(self):
        self.prime_summary();self.assertEqual(self.run_node('run-synth-agent-summary').verdict,'structurally-valid')
        fm=self.mutate('run-synth-agent-summary');output=self.root/'out/summary.json';data=json.loads(output.read_text())
        data['reasoning-trace']['nodes-accessed'].append('concept-mean-exceeds-threshold');output.write_text(json.dumps(data))
        self.assertFalse(runner.verify_structural(fm,self.graph,self.root)['passed'])
        data['reasoning-trace']['nodes-accessed'].pop();data['reasoning-trace']['retriever-manifest']={'embedding-model':'name-only'};output.write_text(json.dumps(data))
        self.assertFalse(runner.verify_structural(fm,self.graph,self.root)['passed'])

    def test_bypass_cannot_count_as_reproduction_or_update_baseline(self):
        v=self.run_node(no_gate=True)
        self.assertEqual(v.verdict,'unchecked')
        path=self.graph[self.mean][0];before=runner.read_sidecar(path)[0]['outputs'][0]['expected-hash']
        runner.write_verdict_back(self.rokb,self.mean,v)
        fm=runner.read_sidecar(path)[0]
        self.assertEqual(fm['status'],'failed');self.assertEqual(fm['outputs'][0]['expected-hash'],before)

    def test_manifest_separates_execution_and_reproduction(self):
        rows=[self.run_node(mode='run'),self.run_node()]
        manifest=runner.write_manifest(rows,self.root/'manifest.json')
        self.assertEqual(manifest['summary']['execution'],{'executed':1})
        self.assertEqual(manifest['summary']['reproduction'],{'normalized-match':1})
        self.assertNotIn('reproducibility-rate-pct',manifest['summary'])

    def test_equivalence_observed_outputs(self):
        verdict=runner.certify_equivalence(self.rokb,self.mean,'run-synth-mean-fast',no_container=True)
        self.assertTrue(verdict.equivalent)
        # Shared output path must not cause B to overwrite the evidence used for A.
        path=self.graph['run-synth-mean-fast'][0];fm=runner.read_sidecar(path)[0]
        fm['outputs'][0]['output-path']='out/mean.json'
        fm['command']='python3 code/compute_mean_fast.py inputs/signal.json out/mean.json'
        import yaml
        path.write_text('---\n'+yaml.safe_dump(fm)+'---\n')
        script=self.root/'code/compute_mean_fast.py';script.write_text(script.read_text().replace('total / n','99.0'))
        self.assertFalse(runner.certify_equivalence(self.rokb,self.mean,'run-synth-mean-fast',no_container=True).equivalent)

    def test_equivalence_empty_or_unequal_outputs_fails(self):
        a=runner.RunVerdict(node='a',mode='run',verdict='executed')
        b=runner.RunVerdict(node='b',mode='run',verdict='executed')
        with patch.object(runner,'run_node',side_effect=[a,b]):
            self.assertFalse(runner.certify_equivalence(self.rokb,self.mean,'run-synth-mean-fast').equivalent)

    def test_project_root_layouts(self):
        self.assertEqual(runner.project_root(self.rokb),self.root.resolve())
        self.assertEqual(runner.project_root(self.root),self.root.resolve())
        custom=self.root/'custom-graph'
        self.assertEqual(runner.project_root(custom,explicit=self.root),self.root.resolve())

    def test_cycle_fails(self):
        graph={
            'a':(None,{'edges':[{'type':'regenerates','target':'x'},{'type':'consumes','target':'y'}]}),
            'b':(None,{'edges':[{'type':'regenerates','target':'y'},{'type':'consumes','target':'x'}]}),
        }
        with self.assertRaises(ValueError):runner.order_runs(graph,['a','b'])

    def test_cli_missing_node_with_writeback_has_clean_failure(self):
        rc=subprocess.run([sys.executable,'-m','glimmer.tools.cli','rerun',str(self.rokb),'no-such-node','--write-verdict','--no-container'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(rc.returncode,1);self.assertNotIn('Traceback',rc.stderr)

    def test_duplicate_producers_and_index_ids_fail(self):
        graph={
            'a':(None,{'edges':[{'type':'regenerates','target':'x'}]}),
            'b':(None,{'edges':[{'type':'regenerates','target':'x'}]}),
        }
        with self.assertRaises(ValueError):runner.order_runs(graph,['a','b'])
        index=self.rokb/'_glimmer-index.json';data=json.loads(index.read_text());data['nodes'].append(data['nodes'][0]);index.write_text(json.dumps(data))
        with self.assertRaises(ValueError):runner.load_graph(self.rokb)

    def test_failure_manifest_is_valid_json_for_nonfinite_observations(self):
        v=runner.RunVerdict(node='bad',mode='reproduce',verdict='mismatch',numeric_checks=[{'observed':float('nan'),'tol':{'abs':float('inf')},'passed':False}])
        path=self.root/'manifest.json';runner.write_manifest([v],path)
        parsed=json.loads(path.read_text(),parse_constant=lambda value: self.fail('invalid JSON constant: '+value))
        self.assertEqual(parsed['runs'][0]['numeric-checks'][0]['observed'],'nan')

    def test_numeric_overflow_cannot_create_infinite_tolerance(self):
        self.assertFalse(runner._tol_pass(1e308,-1e308,{'rel':1e308}))
        self.assertFalse(runner._tol_pass(10**1000,1,{}))

    def test_raw_fallback_does_not_count_as_normalized_match(self):
        path=self.root/'image.nii.gz';path.write_bytes(b'not a nifti')
        pin={'node':'test','output-path':path.name,'tier':'normalized-content','expected-hash':runner.sha256_file(path)}
        self.assertFalse(runner.verify_byte_identical(pin,self.root)['passed'])


if __name__=='__main__':
    unittest.main()
