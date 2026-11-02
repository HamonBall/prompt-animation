"""Pure negative checks: no broad stale-source or changed-output reuse."""
import copy,unittest
from tools.fingers_provenance import sequence_only_change,compatible_record,OLD_LINE,NEW_LINE


class FingerProvenanceTests(unittest.TestCase):
    def test_only_the_exact_sequence_filter_is_compatible(self):
        old='prefix\n'+OLD_LINE+'\nsuffix'
        self.assertTrue(sequence_only_change(old,old.replace(OLD_LINE,NEW_LINE)))
        for changed in (old,old.replace(OLD_LINE,NEW_LINE)+'\n# other change',old.replace(OLD_LINE,'for key in ():')):
            self.assertFalse(sequence_only_change(old,changed))
        self.assertFalse(sequence_only_change(old+OLD_LINE,(old+OLD_LINE).replace(OLD_LINE,NEW_LINE)))

    def test_exact_pinned_non_sequence_only_and_all_negative_identity_cases(self):
        plan={'owner':'stage-05.3b-sequence-fixture','schema_version':1,'status':'verified_unexecuted_branch_change',
              'previous_harness_sha256':'old','current_harness_sha256':'new',
              'cases':{'mixamo/fist':{'inputs':{'producer_sha256':'app','profile.json':'profile'},'result_sha256':'result','motion_sha256':'motion','motion_mtime_ns':3}}}
        def valid(p=plan,**changes):
            args={'key':'mixamo/fist','fixture':'neutral','previous':'old','current':'new',
                  'inputs':{'producer_sha256':'app','profile.json':'profile'},'result_sha':'result','motion_sha':'motion','mtime_ns':3}
            args.update(changes);return compatible_record(p,**args)
        self.assertTrue(valid())
        for changes in ({'key':'unpinned'},{'fixture':'sequence'},{'previous':'other'},{'current':'other'},
                        {'inputs':{'producer_sha256':'changed','profile.json':'profile'}},{'inputs':{'producer_sha256':'app','profile.json':'other'}},
                        {'result_sha':'other'},{'motion_sha':'other'},{'mtime_ns':4}):self.assertFalse(valid(**changes))
        for key,value in (('owner','other'),('schema_version',2),('status','prepared')):
            p=copy.deepcopy(plan);p[key]=value;self.assertFalse(valid(p))


if __name__=='__main__':unittest.main()
