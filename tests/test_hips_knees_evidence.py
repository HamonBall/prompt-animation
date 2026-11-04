"""Cache refusal for changed inputs/runtime/harness and failed native processes."""
import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
from tools import legs_evidence as evidence
from tools.artifact_store import digest


class LegEvidenceTests(unittest.TestCase):
    def test_cache_requires_consistent_process_source_runtime_inputs_and_harness(self):
        scratch=evidence.OUT/'.scratch';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch,prefix='cache-contract-') as folder:
            out=Path(folder);inputs={'producer_sha256':'app','profile.json':'profile'}
            source='tests/blender_movement_hips_knees.py'
            result={'review':{'passed':True},'stage_05_4':{'application_producer_sha256':'app','stage_producer':{source:digest(evidence.ROOT/source)}}}
            (out/'execution.log').write_text(evidence.BUILD+'\nLEGS_NUMERIC_PASSED\nBlender quit\n')
            process={'exit_code':0,'runtime_lock_sha256':'runtime','log_sha256':digest(out/'execution.log'),'producer_at_start':'app'}
            def write():
                (out/'result.json').write_text(json.dumps(result));(out/'native-process.json').write_text(json.dumps(process))
            with patch.object(evidence,'validate_manifest',return_value=({'inputs':inputs},None,None)),patch('tools.hips_knees_provenance.input_identity',return_value=dict(inputs)),patch.object(evidence,'runtime',return_value='runtime'):
                write();self.assertTrue(evidence.numeric_valid(out))
                for key,bad in (('exit_code',1),('runtime_lock_sha256','changed'),('log_sha256','changed'),('producer_at_start','changed')):
                    old=process[key];process[key]=bad;write();self.assertFalse(evidence.numeric_valid(out),key);process[key]=old
                write()
                with patch('tools.hips_knees_provenance.input_identity',return_value={**inputs,'profile.json':'changed'}):self.assertFalse(evidence.numeric_valid(out))
                result['stage_05_4']['stage_producer'][source]='changed';write();self.assertFalse(evidence.numeric_valid(out))
                result['stage_05_4']['stage_producer'][source]=digest(evidence.ROOT/source);write()
                (out/'native-process.json').unlink();self.assertFalse(evidence.numeric_valid(out))
        if scratch.exists() and not any(scratch.iterdir()):scratch.rmdir()


if __name__=='__main__':unittest.main()
