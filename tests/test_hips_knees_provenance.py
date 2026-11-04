"""Only an exact unreachable planted-only branch can preserve free-leg evidence."""
from copy import deepcopy
import unittest
from tools.hips_knees_provenance import BLOCK,branch_only,compatible,execution_identity


class LegBranchProvenanceTests(unittest.TestCase):
    def test_exact_branch_and_pinned_free_leg_identity_are_required(self):
        previous='before\nafter\n';current='before\n'+BLOCK+'after\n'
        plan={'owner':'05.4-planted-rebase','schema_version':1,'status':'verified_unreachable_branch',
              'current_producer_sha256':'new','previous_producer_sha256':'old'}
        manifest={'inputs':{'producer_sha256':'old','result.json':'result'},'state':{'rig':'unchanged'}}
        record={'inputs':deepcopy(manifest['inputs']),'execution_identity':execution_identity(manifest)}
        result={'stage_05_4':{'application_producer_sha256':'old','case':'leg.swing.default.left'}}
        executable={'entry_snapshot':{'profile_version':7},'tracks':[{'control_id':'left.foot.position'}]}
        def check(p=plan,r=record,m=manifest,z=result,x=executable,old=previous,new=current,producer='new'):
            return compatible(p,r,m,z,x,current_producer=producer,previous_source=old,current_source=new)
        self.assertTrue(check())
        self.assertFalse(check(new=current+'extra behavior\n'))
        self.assertFalse(check(old=previous+'changed\n'))
        self.assertFalse(branch_only(previous,current+BLOCK))
        self.assertFalse(check(producer='another app version'))
        for name,bad in (('status','prepared'),('owner','unknown'),('schema_version',2)):
            changed={**plan,name:bad};self.assertFalse(check(p=changed))
        changed=deepcopy(manifest);changed['inputs']['result.json']='changed';self.assertFalse(check(m=changed))
        changed=deepcopy(manifest);changed['state']['rig']='changed';self.assertFalse(check(m=changed))
        changed=deepcopy(result);changed['stage_05_4']['case']='knee.pulse.minimum';self.assertFalse(check(z=changed))
        changed=deepcopy(result);changed['stage_05_4']['application_producer_sha256']='different';self.assertFalse(check(z=changed))
        for key in ('pelvis.position','pelvis.orientation'):
            changed=deepcopy(executable);changed['tracks'].append({'control_id':key});self.assertFalse(check(x=changed))
        changed=deepcopy(executable);changed['entry_snapshot']['profile_version']=6;self.assertFalse(check(x=changed))


if __name__=='__main__':unittest.main()
