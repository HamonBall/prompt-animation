"""Typed-fragment rig adapter used by the existing motion baking transaction."""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector

from ..movement_library import contracts as c
from ..movement_library.compiler import ExecutionCursor, sample_motion, value_error, supporting_chains, check_goal_coverage
from ..movement_library.registry import validate_fragment, validate_snapshot
from ..motion import ContactConstraint
from . import rig_profile as rp
from .pose import position_hand, axes

ANGULAR_CHAINS=('head','neck','torso','spine.mid','spine.upper')


class FragmentAdapter:
    def __init__(self,handle,motion,profile):
        if type(profile) is not c.AvatarProfile:
            c.fail('INVALID_PARAMETER','ExecutableMotion requires its calibrated profile')
        rp._binding(handle,profile)
        validate_snapshot(motion.entry_snapshot,profile)
        check_goal_coverage(motion.goal_checks,motion.duration_s,motion.fps)
        if motion.loop is not None: c.fail('UNSUPPORTED_GOAL','Single-fragment execution does not expand loops')
        self.handle,self.motion,self.profile=handle,motion,profile
        self.cursor=ExecutionCursor()
        self.controls={v.id:v for v in profile.controls}
        self.joints={v.semantic_id:v for v in profile.rest_to_semantic_mappings}
        self.limits={v.control_id:v for v in profile.joint_limits}
        self.owned={self.controls[t.control_id].chain for t in motion.tracks if t.control_id in self.controls}
        self.owned.update(supporting_chains(t.control_id for t in motion.tracks))
        surfaces={s.name:s for s in handle.surfaces}
        surfaces.setdefault('floor',None)
        fragment=c.MotionFragment('execution.preflight',tuple(sorted({s for t in (*motion.tracks,*motion.contact_events) for s in t.source_instance_ids})) or ('empty',),
            (),motion.duration_s,motion.tracks,motion.contact_events,(),(),motion.goal_checks)
        validate_fragment(fragment,profile,resolved_surface_ids=tuple(surfaces))
        for track in motion.tracks:
            control=self.controls[track.control_id]
            if control.chain in ANGULAR_CHAINS and control.value_shape=='scalar': continue
            if track.control_id.endswith('.hand.position'):
                for value in (track.curve.start_value,track.curve.end_value):
                    if value is not None: self._check_reach(track.control_id,value)
                continue
            c.fail('MISSING_CAPABILITY','No tested application adapter for this measured control yet',control_id=track.control_id)
        for event in motion.contact_events:
            if event.anchor_id not in ('left.sole','right.sole') or event.surface_id!='floor':
                c.fail('MISSING_CAPABILITY','Stage 04 supports existing floor sole anchors',details={'anchor_id':event.anchor_id})
            if event.clearance_m!=0:
                c.fail('UNSUPPORTED_GOAL','Floor sole support requires zero surface clearance')
        actual=rp.capture_motion_state(handle,profile,revision=motion.entry_snapshot.revision,captured_time_s=0)
        expected={v.control_id:v for v in motion.entry_snapshot.measured_controls}
        self._entry_errors=[]
        for value in actual.measured_controls:
            saved=expected.get(value.control_id)
            if saved is None: c.fail('ENTRY_MISMATCH','Entry snapshot is incomplete',control_id=value.control_id)
            control=self.controls[value.control_id]
            error=value_error(value.value,saved.value,control.value_shape)
            tolerance=.001 if control.unit=='metre' else .05 if control.unit=='degree' else 1e-4
            if error>tolerance:
                c.fail('ENTRY_MISMATCH','Current solved rig differs from supplied entry; capture it again',
                       control_id=value.control_id,details={'error':error,'tolerance':tolerance})
            self._entry_errors.append(error)
        self.measured=motion.entry_snapshot
        self.basis={b.name:b.matrix_basis.copy() for b in handle.rig.pose.bones}
        self.anchors={a.anchor_id:Vector(a.position) for a in motion.entry_snapshot.contact_anchors}
        for anchor in motion.entry_snapshot.active_contacts:
            if anchor not in ('left.sole','right.sole'):
                c.fail('MISSING_CAPABILITY','Entry support anchor has no Stage 04 adapter',details={'anchor_id':anchor})
            if (Vector(rp.measure_endpoint(handle,profile,anchor))-self.anchors[anchor]).length>.025:
                c.fail('ENTRY_MISMATCH','Captured active anchor differs from the solved support',details={'anchor_id':anchor})
        self.foot_orientations={s:handle.bones[s.title()+'Foot'].matrix.to_quaternion().copy() for s in ('left','right')}
        self.diagnostics=[]

    def _check_reach(self,control_id,target):
        h=self.handle; side=control_id.split('.')[0].title(); world=h.rig.matrix_world
        a=world @ h.bones[side+'Arm'].head
        b=world @ h.bones[side+'ForeArm'].head
        end=world @ h.bones[side+'Hand'].head
        first,second=(b-a).length,(end-b).length
        distance=(Vector(target)-a).length
        if distance>first+second+1e-5 or distance<=abs(first-second)+1e-5:
            c.fail('INVALID_PARAMETER','Hand target is unreachable from this measured shoulder',control_id=control_id,
                   details={'distance_m':distance,'reach_m':first+second})

    def _angular(self,chain,requested):
        h,p=self.handle,self.profile
        mapping=self.joints[chain]
        bone=h.rig.pose.bones[mapping.source_bones[0]]
        ids=[v.id for v in p.controls if v.chain==chain and v.value_shape=='scalar']
        axes_by_id={id:Vector(self.limits[id].positive_axis) for id in ids}
        # Swing/twist measurements satisfy dot(v/w, axis_i)=tan(angle_i/2).
        # Solve all three anatomical components together, preserving unowned ones.
        matrix=Matrix(tuple(axes_by_id[id] for id in ids))
        if len(ids)!=3 or abs(matrix.determinant())<1e-6:
            c.fail('MISSING_CAPABILITY','This chain needs a dedicated calibrated application adapter')
        values=[requested.get(id,rp.measure_joint_angle(h,p,id)) for id in ids]
        tangent=matrix.inverted() @ Vector(tuple(math.tan(math.radians(v)/2) for v in values))
        delta=Quaternion((1,*tangent)).normalized()
        parent=rp.semantic_frame(h,p,mapping.parent_id)
        rotation=parent.to_quaternion() @ delta @ Quaternion(mapping.rest_to_semantic.orientation)
        world=h.rig.matrix_world @ bone.matrix
        desired=Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1))
        bone.matrix=h.rig.matrix_world.inverted() @ desired
        bpy.context.view_layer.update()

    def step(self,time_s,frame):
        from .motion import capture_sample, set_contact, contact_ease
        h,p=self.handle,self.profile
        for bone in h.rig.pose.bones:
            bone.rotation_mode='QUATERNION'; bone.matrix_basis=self.basis[bone.name]
        bpy.context.view_layer.update()
        targets=sample_motion(self.motion,time_s,self.measured,self.cursor)
        requested={v.control_id:v.value for v in targets.controls}
        chains=sorted({self.controls[id].chain for id in requested},
                      key=lambda id:(sum(1 for _ in self._parents(id)),id))
        for chain in chains:
            if chain in ANGULAR_CHAINS: self._angular(chain,requested)
        for value in targets.controls:
            if not value.control_id.endswith('.hand.position'): continue
            side=value.control_id.split('.')[0].title()
            current=Vector(rp.measure_endpoint(h,p,side.lower()+'.hand'))
            if (current-Vector(value.value)).length>1e-7:
                self._check_reach(value.control_id,value.value)
                pole=Vector(rp.measure_bend_plane(h,p,side.lower()+'.forearm'))
                shoulder=h.rig.matrix_world @ h.bones[side+'Arm'].head
                elbow=h.rig.matrix_world @ h.bones[side+'ForeArm'].head
                axis=(current-shoulder).normalized()
                bent=elbow-shoulder-axis*(elbow-shoulder).dot(axis)
                pole_point=elbow if bent.length>1e-5 else shoulder+pole*p.height_m*.3
                target=h.rig.matrix_world.inverted() @ Vector(value.value)
                position_hand(h,side,target,axes(h),pole=h.rig.matrix_world.inverted() @ pole_point)
        errors={}; active=[]
        for event in targets.active_contacts:
            side=event.anchor_id.split('.')[0]
            position=Vector(rp.measure_endpoint(h,p,event.anchor_id))
            if event.anchor_id not in self.anchors:
                self.anchors[event.anchor_id]=Vector((position.x,position.y,0))
            anchor=self.anchors[event.anchor_id]
            acquire=1 if event.acquire_s==0 else min(1,(time_s-event.interval.start_s)/event.acquire_s)
            release=1 if event.release_s==0 else min(1,(event.interval.end_s-time_s)/event.release_s)
            weight=contact_ease(max(0,min(acquire,release)))
            if weight>1e-8:
                active.append(event.anchor_id)
                delta=(anchor-position)*weight
                if delta.length>1e-6:
                    foot=h.bones[side.title()+'Foot']
                    target=foot.head+h.rig.matrix_world.inverted().to_3x3() @ delta
                    set_contact(h,ContactConstraint(side+'_foot'),target,self.foot_orientations[side])
                errors[side+'_foot']=(Vector(rp.measure_endpoint(h,p,event.anchor_id))-anchor).length*weight
        anchors=tuple(c.ContactAnchor(id,'floor',tuple(self.anchors[id]),'world','metre') for id in active)
        solved=rp.capture_motion_state(h,p,revision=self.motion.entry_snapshot.revision,captured_time_s=time_s,
                                      contact_anchors=anchors,active_contacts=tuple(active))
        measured={v.control_id:v for v in solved.measured_controls}
        violations=[]
        tracking={}
        for target in targets.controls:
            control=self.controls[target.control_id]
            error=value_error(measured[control.id].value,target.value,control.value_shape)
            tracking[control.id]=error
            tolerance=3 if control.unit=='degree' or control.value_shape=='quaternion' else .01
            if error>tolerance: violations.append(('tracking_residual',control.id,error,tolerance))
        for goal in targets.expected_goals:
            control=self.controls[goal.target.control_id]
            error=value_error(measured[control.id].value,goal.target.value,control.value_shape)
            tolerance=min(goal.tolerance,3 if control.unit=='degree' or control.value_shape=='quaternion' else .01)
            if error>tolerance: violations.append(('incomplete_goal',control.id,error,tolerance))
        entry={v.control_id:v for v in self.motion.entry_snapshot.measured_controls}
        unrelated=0
        for id,value in measured.items():
            control=self.controls[id]
            if any(control.chain==owned or owned in tuple(self._parents(control.chain)) for owned in self.owned): continue
            error=value_error(value.value,entry[id].value,control.value_shape)
            tolerance=.002 if control.unit=='metre' else .5 if control.unit=='degree' or control.value_shape=='quaternion' else .008726535
            unrelated=max(unrelated,error)
            if error>tolerance: violations.append(('unrelated_change',id,error,tolerance))
        # Unowned angular components on an owned head/spine chain are explicit locks.
        for id,value in measured.items():
            if id in requested or self.controls[id].chain not in ANGULAR_CHAINS: continue
            error=value_error(value.value,entry[id].value,self.controls[id].value_shape)
            if error>.5: violations.append(('unrelated_change',id,error,.5))
        sample=capture_sample(h,frame,','.join(targets.source_instance_ids),errors)
        sample['controls']={v.control_id:v.value for v in solved.measured_controls}
        sample['semantic_violations']=violations
        details={'frame':frame,'time_s':time_s,'source_instance_ids':list(targets.source_instance_ids),
            'targets':{v.control_id:v.value for v in targets.controls},'measured':sample['controls'],
            'checked_goal_ids':[g.goal_id for g in targets.expected_goals],
            'tracking_errors':tracking,'contacts':dict(errors),'floor_m':sample['floor'],'violations':violations}
        self.diagnostics.append(details)
        sample['semantic_details']=details
        sample['snapshot']=solved
        self.measured=solved
        self.basis={b.name:b.matrix_basis.copy() for b in h.rig.pose.bones}
        return sample

    def _parents(self,joint):
        current=self.joints[joint].parent_id
        while current is not None:
            yield current
            current=self.joints[current].parent_id

    def finish(self,report):
        from .motion import MotionIssue
        checked={id for sample in self.diagnostics for id in sample['checked_goal_ids']}
        for goal in self.motion.goal_checks:
            if goal.goal_id not in checked:
                report.issues.append(MotionIssue('unmeasured_goal',self.diagnostics[-1]['frame'],goal.goal_id,1,0))
        for sample in self.diagnostics:
            for kind,control,error,tolerance in sample['violations']:
                report.issues.append(MotionIssue(kind,sample['frame'],control,error,tolerance,','.join(sample['source_instance_ids'])))
        report.metrics['semantic_frames']=len(self.diagnostics)
        return report
