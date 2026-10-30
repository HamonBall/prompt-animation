"""Source migration must never accept changed endpoint paths or mutable payloads."""
import copy,unittest
from tools.hands_source_compatibility import compatible_record


class HandsSourceCompatibilityTests(unittest.TestCase):
    def test_exact_pinned_unchanged_path_and_rejections(self):
        record={'affected':False,'inputs':{'entry.json':'entry'},'motion_sha256':'motion','motion_mtime_ns':7}
        plan={'schema_version':1,'owner':'stage-05.3a-endpoint-baseline-fix','status':'source_compatibility_verified','current_producer_sha256':'new','previous_producer_sha256':'old','cases':{'demo/wrist.flex.default':record}}
        def valid(p=plan,**changes):
            args={'key':'demo/wrist.flex.default','current':'new','execution_producer':'old','ids':['left.wrist.flexion'],
                  'inputs':{'entry.json':'entry'},'motion_sha':'motion','mtime_ns':7};args.update(changes)
            return compatible_record(p,**args)
        self.assertTrue(valid())
        for changes in ({'current':'unknown'},{'execution_producer':'unknown'},{'key':'other'},
                        {'inputs':{'entry.json':'changed'}},{'motion_sha':'changed'},{'mtime_ns':8},
                        {'ids':['left.hand.position']},{'ids':['right.hand.torso_position']},{'ids':['left.elbow.plane']}):
            self.assertFalse(valid(**changes))
        changed=copy.deepcopy(plan);changed['cases']['demo/wrist.flex.default']['affected']=True
        self.assertFalse(valid(changed))
        changed=copy.deepcopy(plan);changed['status']='prepared';self.assertFalse(valid(changed))
        changed=copy.deepcopy(plan);changed['schema_version']=2;self.assertFalse(valid(changed))


if __name__=='__main__':unittest.main()
