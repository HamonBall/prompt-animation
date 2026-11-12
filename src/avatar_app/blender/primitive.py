"""Typed-fragment rig adapter used by the existing motion baking transaction."""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector

from ..movement_library import contracts as c
from ..movement_library.compiler import ExecutionCursor, sample_motion, value_error, supporting_chains, check_goal_coverage
from ..movement_library.coordinated import (
    CRAWL_ANCHORS, CRAWL_ENDPOINTS, KNEE_CRAWL_ANCHORS, KNEE_CRAWL_ENDPOINTS, LEG_CHAINS,
    grounded_root_windows, has_floor_body_transition, has_seated_approach, has_step_support,
    validate_crawl_support,
)
from ..movement_library.registry import validate_fragment, validate_snapshot
from ..movement_library.root_motion import CONTROLS as ROOT_CONTROLS, ORIENTATION, POSITION
from ..movement_library.support import (
    BODY_ANCHORS, FOOT_ANCHORS, PALM_ANCHORS, SOLE_ANCHORS,
    require_surface_point, sole_region_margin, validate_support_drivers,
)
from ..motion import ContactConstraint, Surface
from . import rig_profile as rp
from .pose import position_hand, axes
from .support_mechanics import body_contact_point

ANGULAR_CHAINS=('head','neck','torso','spine.mid','spine.upper','left.clavicle','right.clavicle')


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
        surfaces.setdefault('floor',Surface())
        fragment=c.MotionFragment('execution.preflight',tuple(sorted({s for t in (*motion.tracks,*motion.contact_events) for s in t.source_instance_ids})) or ('empty',),
            (),motion.duration_s,motion.tracks,motion.contact_events,(),(),motion.goal_checks)
        validate_fragment(fragment,profile,resolved_surface_ids=tuple(surfaces))
        track_ids = {track.control_id for track in motion.tracks}
        self.knee_crawl = (
            profile.version == 8 and set(motion.entry_snapshot.active_contacts) == set(KNEE_CRAWL_ANCHORS)
            and {event.anchor_id for event in motion.contact_events} == set(KNEE_CRAWL_ANCHORS)
            and all(event.target_world_v1 is not None and event.surface_id == 'floor' for event in motion.contact_events)
            and track_ids == {'pelvis.position', *KNEE_CRAWL_ENDPOINTS}
        )
        self.moves_root = bool(track_ids & ROOT_CONTROLS)
        self.root_leg_windows = grounded_root_windows(motion, track_ids) if self.moves_root else ()
        if self.moves_root:
            if profile.version != 8 or (track_ids != ROOT_CONTROLS and not self.root_leg_windows):
                c.fail('CONSTRAINT_CONFLICT', 'Root fragments require both object controls and compatible planted articulation')
            rig = handle.rig
            if (rig.constraints or rig.animation_data and rig.animation_data.drivers
                    or rig.parent and rig.parent_type != 'OBJECT'
                    or rig.delta_location.length_squared or rig.delta_rotation_euler.to_quaternion().angle
                    or abs(rig.delta_rotation_quaternion.w) != 1 or tuple(rig.delta_scale) != (1, 1, 1)
                    or min(rig.scale) <= 0):
                c.fail('MISSING_CAPABILITY', 'Root baking requires ordinary positive armature transforms without constraints or drivers')
            parent = rig.parent
            while parent:
                animation = parent.animation_data
                if (parent.constraints or animation and (animation.action or animation.drivers or animation.nla_tracks)
                        or parent.parent and parent.parent_type != 'OBJECT'):
                    c.fail('MISSING_CAPABILITY', 'Root baking requires a static object parent hierarchy')
                parent = parent.parent
            parent_frame = rp.object_parent_frame(rig)
            if rp.uniform_parent_scale(parent_frame) is None:
                c.fail('MISSING_CAPABILITY', 'Root baking requires an orthogonal uniformly scaled parent frame')
            self.root_parent_inverse = parent_frame.inverted()
            self.root_parent_rotation_inverse = parent_frame.to_quaternion().conjugated()
            self.root_scale = rig.scale.copy()
            self.root_entry = rig.matrix_world.copy()
            if any(not any(event.anchor_id == anchor and event.interval.start_s == 0 for event in motion.contact_events)
                   for anchor in motion.entry_snapshot.active_contacts):
                c.fail('CONSTRAINT_CONFLICT', 'Root fragments need explicit continuation or release of every captured sole')
            for event in motion.contact_events:
                if event.anchor_id not in motion.entry_snapshot.active_contacts or not event.anchor_id.endswith('.sole'):
                    c.fail('CONSTRAINT_CONFLICT', 'Root motion can only retain or release captured soles')
        head_modes={t.control_id for t in motion.tracks if t.control_id in ('head.orientation','head.torso_orientation')}
        if len(head_modes)>1 or head_modes and any(t.control_id in ('head.pitch','head.yaw','head.roll') for t in motion.tracks):
            c.fail('CONSTRAINT_CONFLICT','Head orientation and individual head angles cannot own the same fragment')
        for track in motion.tracks:
            control=self.controls[track.control_id]
            if self.moves_root: continue
            if profile.version in (7,8) and track.control_id.endswith(('.hip.flexion','.hip.abduction','.hip.rotation','.knee.flexion','.knee.plane','.foot.position','.foot.orientation')):continue
            if profile.version==8 and track.control_id.endswith(('.ankle.flexion','.ankle.tilt','.toe.flexion')):continue
            if track.control_id in ('pelvis.position','pelvis.orientation'): continue
            if self.knee_crawl and track.control_id.endswith('.knee.support.position'): continue
            if track.control_id in head_modes: continue
            if track.control_id.endswith('.upper_arm.orientation'):continue
            if profile.version in (6,7,8) and '.finger.' in track.control_id and control.value_shape=='scalar':continue
            if profile.version in (5,6,7,8) and '.hand.torso_' in track.control_id:continue
            if profile.version in (5,6,7,8) and track.control_id.endswith(('.elbow.flexion','.elbow.plane','.forearm.twist','.wrist.flexion','.wrist.deviation','.hand.orientation')):continue
            if control.chain in ANGULAR_CHAINS and control.value_shape=='scalar': continue
            if track.control_id.endswith('.hand.position'):
                for value in (track.curve.start_value,track.curve.end_value):
                    if value is not None: self._check_reach(track.control_id,value)
                continue
            c.fail('MISSING_CAPABILITY','No tested application adapter for this measured control yet',control_id=track.control_id)
        parts=('sole','heel','forefoot') if profile.version==8 else ('sole',)
        floor_anchors={side+'.'+part for side in ('left','right') for part in parts}
        captured={a.anchor_id:a for a in motion.entry_snapshot.contact_anchors}
        self.fixed_support = any(event.target_world_v1 is not None for event in motion.contact_events)
        self.fixed_surfaces = {}
        self.balance_track = None
        self.body_support = any(event.anchor_id in BODY_ANCHORS for event in motion.contact_events) and self.fixed_support
        self.fixed_pelvis = self.fixed_support and 'pelvis.position' in track_ids
        self.tracked_body_contact = self.fixed_support and (
            has_seated_approach(motion, track_ids) or has_floor_body_transition(motion, track_ids))
        four_point_support = (set(motion.entry_snapshot.active_contacts) == set(CRAWL_ANCHORS)
                              and {event.anchor_id for event in motion.contact_events} == set(CRAWL_ANCHORS)
                              and track_ids == {'pelvis.position', *CRAWL_ENDPOINTS})
        coordinated_support = self.fixed_support and (four_point_support or self.knee_crawl or self.tracked_body_contact or has_step_support(
            motion.entry_snapshot, motion.contact_events, track_ids, motion.duration_s))
        if self.fixed_support and (profile.version != 8
                                   or any(event.target_world_v1 is None for event in motion.contact_events)
                                   or (track_ids - {'pelvis.position'} and not coordinated_support)):
            c.fail('CONSTRAINT_CONFLICT', 'Fixed support needs profile 8 and a compatible set of tracked controls')
        if self.fixed_support and motion.tracks and not coordinated_support:
            if len(motion.tracks) != 1 or len(motion.contact_events) != 1:
                c.fail('CONSTRAINT_CONFLICT', 'Balance requires one pelvis approach and one held sole')
            event, = motion.contact_events
            track, = motion.tracks
            if (event.anchor_id not in SOLE_ANCHORS or event.anchor_id not in motion.entry_snapshot.active_contacts
                    or event.surface_id != 'floor'
                    or event.acquire_s or event.release_s or event.interval != c.TimeInterval(0, motion.duration_s)
                    or track.interval.start_s != 0 or track.interval.end_s >= motion.duration_s):
                c.fail('ENTRY_MISMATCH', 'Balance needs one captured floor sole through approach and hold')
            self.balance_track = track
        if self.fixed_support:
            if four_point_support or self.knee_crawl:
                validate_crawl_support(motion.contact_events, motion.duration_s)
            for index, first in enumerate(motion.contact_events):
                for second in motion.contact_events[index + 1:]:
                    if max(first.interval.start_s, second.interval.start_s) > min(first.interval.end_s, second.interval.end_s):
                        continue
                    if not self.knee_crawl:
                        validate_support_drivers((first.anchor_id, second.anchor_id))
                    if (first.anchor_id in FOOT_ANCHORS and second.anchor_id in FOOT_ANCHORS
                            and first.anchor_id.split('.')[0] == second.anchor_id.split('.')[0]):
                        c.fail('CONSTRAINT_CONFLICT', 'Fixed targets cannot compete for one leg')
        for event in motion.contact_events:
            if self.fixed_support:
                if (event.anchor_id not in FOOT_ANCHORS + PALM_ANCHORS + BODY_ANCHORS or event.clearance_m != 0
                        or event.anchor_id + '.position' not in self.controls):
                    c.fail('MISSING_CAPABILITY', 'Fixed support needs a calibrated contact point')
                anchor = c.ContactAnchor(event.anchor_id, event.surface_id, event.target_world_v1, 'world', 'metre')
                self.fixed_surfaces[event.surface_id] = require_surface_point(anchor, surfaces.values())
                if event.interval.start_s == 0 and event.anchor_id in motion.entry_snapshot.active_contacts:
                    if event.acquire_s or anchor != captured[event.anchor_id]:
                        c.fail('ENTRY_MISMATCH', 'Continuation must preserve the captured world anchor and surface',
                               details={'anchor_id': event.anchor_id})
                elif event.acquire_s == 0:
                    c.fail('ENTRY_MISMATCH', 'New fixed support needs an explicit acquisition ramp',
                           details={'anchor_id': event.anchor_id})
                elif event.anchor_id in motion.entry_snapshot.active_contacts:
                    previous = max((item for item in motion.contact_events if item.anchor_id == event.anchor_id
                                    and item.interval.start_s < event.interval.start_s),
                                   key=lambda item: item.interval.start_s, default=None)
                    if previous is None or not previous.release_s or previous.interval.end_s >= event.interval.start_s:
                        c.fail('CONSTRAINT_CONFLICT', 'Reacquiring a captured anchor requires an earlier release',
                               details={'anchor_id': event.anchor_id})
                side = event.anchor_id.split('.')[0]
                if event.anchor_id in BODY_ANCHORS:
                    self.owned.add('pelvis')
                    if self.knee_crawl:
                        self.owned.update((side + '.thigh', side + '.shin'))
                else:
                    parts = ('upper_arm', 'forearm', 'wrist') if event.anchor_id in PALM_ANCHORS else ('thigh','shin','ankle')
                    self.owned.update(side+'.'+part for part in parts)
                continue
            if event.anchor_id not in floor_anchors or event.surface_id!='floor':
                c.fail('MISSING_CAPABILITY','Contact needs an available floor foot anchor',details={'anchor_id':event.anchor_id})
            if event.clearance_m!=0:
                c.fail('UNSUPPORTED_GOAL','Floor foot support requires zero surface clearance')
            if event.anchor_id.endswith(('.heel','.forefoot')):
                side=event.anchor_id.split('.')[0]
                anchor=captured.get(event.anchor_id)
                if anchor is None or anchor.frame!='world' or anchor.surface_id!='floor' or abs(anchor.position[2])>.003:
                    c.fail('ENTRY_MISMATCH','Pivot needs a captured world floor reference',details={'anchor_id':event.anchor_id})
                if event.acquire_s or event.release_s:
                    c.fail('UNSUPPORTED_GOAL','Rigid pivot requires a fixed anchor throughout its phase')
                self.owned.update(side+'.'+part for part in ('thigh','shin','ankle'))
        if self.fixed_support and not set(motion.entry_snapshot.active_contacts) <= {
            event.anchor_id for event in motion.contact_events if event.interval.start_s == 0
        }:
            c.fail('ENTRY_MISMATCH', 'Fixed support must continue or release every active entry anchor')
        if profile.version in (7,8):
            for side in ('left','right'):
                ids={t.control_id for t in motion.tracks if t.control_id.startswith(side+'.')}
                if (side+'.foot.position' in ids or side+'.knee.plane' in ids) and any('.hip.' in key or key.endswith('.knee.flexion') for key in ids):
                    c.fail('CONSTRAINT_CONFLICT','Hard foot IK conflicts with independently prescribed hip/knee angles')
                planted=any(e.anchor_id==side+'.sole' and e.interval.start_s==0 and e.interval.end_s==motion.duration_s and e.release_s==0 for e in motion.contact_events)
                if planted and any(t.curve.start_value!=t.curve.end_value and
                        ('.hip.' in t.control_id or t.control_id.endswith(('.knee.flexion','.foot.position'))) for t in motion.tracks if t.control_id in ids):
                    c.fail('CONSTRAINT_CONFLICT','Moving a free leg contradicts its full-duration planted contact')
                if profile.version==8:
                    local={side+'.'+suffix for suffix in ('ankle.flexion','ankle.tilt','toe.flexion')}
                    pivot=any(e.target_world_v1 is None and e.anchor_id in (side+'.heel',side+'.forefoot')
                              for e in motion.contact_events)
                    if pivot and (side+'.foot.orientation' not in ids or any(
                            '.hip.' in key or '.knee.' in key or key==side+'.foot.position' for key in ids)):
                        c.fail('CONSTRAINT_CONFLICT','Pivot requires a foot orientation and owns the supporting IK target')
                    if ids & local and (planted or pivot or side+'.foot.orientation' in ids):
                        c.fail('CONSTRAINT_CONFLICT','Local articulation conflicts with rigid support or foot orientation')
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
        self.arm_entry_basis={name:matrix.copy() for name,matrix in self.basis.items()}
        self.anchors={a.anchor_id:Vector(a.position) for a in motion.entry_snapshot.contact_anchors}
        self.foot_acquisitions=set()
        if profile.version==8 and not self.fixed_support:
            for event in motion.contact_events:
                if event.anchor_id.endswith(('.heel','.forefoot')):
                    point=Vector(rp.measure_endpoint(handle,profile,event.anchor_id))
                    if (point-self.anchors[event.anchor_id]).length>.001:
                        c.fail('ENTRY_MISMATCH','Captured pivot point differs from the measured entry',
                               details={'anchor_id':event.anchor_id})
        for anchor in motion.entry_snapshot.active_contacts:
            if anchor not in floor_anchors and not (self.fixed_support and anchor in PALM_ANCHORS + BODY_ANCHORS):
                c.fail('MISSING_CAPABILITY','Entry support anchor has no Stage 04 adapter',details={'anchor_id':anchor})
            if self.fixed_support and anchor in BODY_ANCHORS:
                point = body_contact_point(handle, profile, anchor, self.fixed_surfaces[captured[anchor].surface_id])
            else:
                point = Vector(rp.measure_endpoint(handle,profile,anchor))
            if (point-self.anchors[anchor]).length>.025:
                c.fail('ENTRY_MISMATCH','Captured active anchor differs from the solved support',details={'anchor_id':anchor})
        self.foot_orientations={s:handle.bones[s.title()+'Foot'].matrix.to_quaternion().copy() for s in ('left','right')}
        self.foot_heads={s:handle.bones[s.title()+'Foot'].head.copy() for s in ('left','right')}
        self.pelvis_entry_orientation=rp.semantic_frame(handle,profile,'pelvis').to_quaternion()
        self.leg_poles={}
        for side in ('left','right'):
            upper,lower,foot=(handle.bones[side.title()+name] for name in ('UpLeg','Leg','Foot'))
            axis=(foot.head-upper.head).normalized()
            bend=lower.head-upper.head-axis*(lower.head-upper.head).dot(axis)
            self.leg_poles[side]=(handle.rig.matrix_world.to_3x3() @ bend.normalized() if bend.length>1e-6
                else Vector(rp.measure_bend_plane(handle,profile,side+'.shin')))
        pelvis_tracks=[t for t in motion.tracks if t.control_id.startswith('pelvis.')]
        if pelvis_tracks and not self.fixed_support:
            if not self.root_leg_windows and (set(motion.entry_snapshot.active_contacts)!={'left.sole','right.sole'} or not all(
                any(e.anchor_id==side+'.sole' and e.interval.start_s==0 and e.interval.end_s==motion.duration_s
                    and e.acquire_s==0 and e.release_s==0 for e in motion.contact_events) for side in ('left','right'))):
                c.fail('ENTRY_MISMATCH','Pelvis adapter requires both captured sole anchors held for the full fragment')
            for track in pelvis_tracks:
                if self.root_leg_windows and not any(
                        window.start_s - 1e-9 <= track.interval.start_s and track.interval.end_s <= window.end_s + 1e-9
                        for window in self.root_leg_windows):
                    continue
                for value in (track.curve.start_value,track.curve.end_value):
                    if value is not None:self._check_pelvis_reach({track.control_id:value})
        self.diagnostics=[]
        self.arm_review=profile.version in (4,5,6,7,8)
        self.previous_arm_poles={}

    def _arm_clearance(self,side):
        """Chest/head and opposite-arm capsules; no skin collision claim."""
        from ..movement_library.curves import segment_distance
        h,p=self.handle,self.profile
        hip=rp.semantic_frame(h,p,'pelvis').translation
        chest=rp.semantic_frame(h,p,next(j for j in ('spine.upper','spine.mid','torso') if j in self.joints)).translation
        head=rp.semantic_frame(h,p,'head').translation
        start=hip.lerp(chest,.35);axis=chest-start
        points=[h.rig.matrix_world @ h.bones[side.title()+name].head for name in ('Arm','ForeArm','Hand')]
        minimum=float('inf')
        for a,b in zip(points,points[1:]):
            for index in range(1,9):
                point=a.lerp(b,index/8)
                t=max(0,min(1,(point-start).dot(axis)/max(axis.length_squared,1e-12)))
                minimum=min(minimum,(point-(start+axis*t)).length-.093*p.height_m,
                            (point-head).length-.083*p.height_m)
        other='right' if side=='left' else 'left'
        opposite=[h.rig.matrix_world @ h.bones[other.title()+name].head for name in ('Arm','ForeArm','Hand')]
        for a,b in zip(points,points[1:]):
            for c0,d in zip(opposite,opposite[1:]):
                minimum=min(minimum,segment_distance(a,b,c0,d)-.036*p.height_m)
        return minimum

    def _check_pelvis_reach(self,requested):
        h,p=self.handle,self.profile
        frame=rp.semantic_frame(h,p,'pelvis')
        rotation=Quaternion(requested.get('pelvis.orientation',tuple(frame.to_quaternion()))) @ frame.to_quaternion().conjugated()
        position=Vector(requested.get('pelvis.position',tuple(frame.translation)))
        for side in ('left','right'):
            upper,lower,foot=(h.bones[side.title()+name] for name in ('UpLeg','Leg','Foot'))
            hip=h.rig.matrix_world @ upper.head
            hip=position+rotation @ (hip-frame.translation)
            a=(h.rig.matrix_world.to_3x3() @ (lower.head-upper.head)).length
            b=(h.rig.matrix_world.to_3x3() @ (foot.head-lower.head)).length
            distance=(h.rig.matrix_world @ self.foot_heads[side]-hip).length
            if distance>a+b+1e-5 or distance<abs(a-b)+1e-5:
                c.fail('INVALID_PARAMETER','Pelvis request exceeds the captured planted-leg reach',details={'side':side,'distance_m':distance,'reach_m':a+b})

    def _apply_pelvis_transform(self, requested):
        h,p=self.handle,self.profile
        bone=h.rig.pose.bones[self.joints['pelvis'].source_bones[0]]
        semantic=rp.semantic_frame(h,p,'pelvis')
        position=Vector(requested.get('pelvis.position',tuple(semantic.translation)))
        orientation=requested.get('pelvis.orientation',tuple(semantic.to_quaternion()))
        if (position-semantic.translation).length<1e-8 and value_error(orientation,tuple(semantic.to_quaternion()),'quaternion')<1e-4:
            return  # An identity request must not re-solve a captured straight knee.
        world=h.rig.matrix_world @ bone.matrix
        rotation=Quaternion(orientation) @ semantic.to_quaternion().conjugated() @ world.to_quaternion()
        bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(position) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
        bpy.context.view_layer.update()
        return Quaternion(orientation)

    def _pelvis(self,requested):
        from .motion import set_contact
        h = self.handle
        self._check_pelvis_reach(requested)
        orientation = self._apply_pelvis_transform(requested)
        if orientation is None:
            return
        for side in ('left','right'):
            try:
                delta=orientation @ self.pelvis_entry_orientation.conjugated()
                pole=h.rig.matrix_world.inverted().to_3x3() @ (delta @ self.leg_poles[side])
                set_contact(h,ContactConstraint(side+'_foot'),self.foot_heads[side],self.foot_orientations[side],leg_pole=pole)
            except ValueError:
                c.fail('INVALID_PARAMETER','Pelvis request exceeds the captured planted-leg reach',details={'side':side})

    def _leg_pole(self,side):
        rotation=rp.semantic_frame(self.handle,self.profile,'pelvis').to_quaternion() @ self.pelvis_entry_orientation.conjugated()
        return self.handle.rig.matrix_world.inverted().to_3x3() @ (rotation @ self.leg_poles[side])

    def _fixed_foot(self, event, goal):
        from .motion import set_contact

        h, p = self.handle, self.profile
        side = event.anchor_id.split('.')[0]
        foot = h.bones[side.title() + 'Foot']
        inverse = h.rig.matrix_world.inverted()
        point = inverse @ Vector(rp.measure_endpoint(h, p, event.anchor_id))
        current = foot.matrix.to_quaternion()
        orientation = self.foot_orientations[side]
        if (inverse @ goal - point).length <= 1e-6 and value_error(tuple(current), tuple(orientation), 'quaternion') <= 1e-4:
            return
        offset = orientation @ current.conjugated() @ (point - foot.head)
        target = inverse @ goal - offset
        try:
            set_contact(h, ContactConstraint(side + '_foot', event.surface_id), target,
                        orientation, leg_pole=self._leg_pole(side))
        except ValueError:
            c.fail('INVALID_PARAMETER', 'The fixed support point is unreachable',
                   details={'anchor_id': event.anchor_id, 'surface_id': event.surface_id})

    def _translate_pelvis(self, delta):
        pelvis = rp.semantic_frame(self.handle, self.profile, 'pelvis').translation
        self._apply_pelvis_transform({'pelvis.position': tuple(pelvis + delta)})

    def _check_reach(self,control_id,target):
        if Vector(target).length>20:
            c.fail('RESOURCE_LIMIT','Solved hand target exceeds the 20 metre workspace',control_id=control_id)
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
        grounded_articulation = 'pelvis.position' in requested and any(
            window.start_s - 1e-9 <= time_s <= window.end_s + 1e-9 for window in self.root_leg_windows)
        apply_pelvis = (any(key in requested for key in ('pelvis.position', 'pelvis.orientation'))
                        and (not self.moves_root or grounded_articulation))
        if self.moves_root:
            if not ROOT_CONTROLS <= requested.keys():
                c.fail('ENTRY_MISMATCH', 'Object root tracks must begin at the measured entry')
            root = h.rig
            root.rotation_mode = 'QUATERNION'
            root.location = self.root_parent_inverse @ Vector(requested[POSITION])
            root.rotation_quaternion = self.root_parent_rotation_inverse @ Quaternion(requested[ORIENTATION])
            root.scale = self.root_scale
            bpy.context.view_layer.update()
        if not self.fixed_support and p.version in (7,8) and apply_pelvis:
            pelvis=h.rig.pose.bones[self.joints['pelvis'].source_bones[0]]
            pelvis.matrix_basis=self.arm_entry_basis[pelvis.name]
            for side in ('left','right'):
                for part in ('UpLeg','Leg','Foot'):
                    bone=h.bones[side.title()+part]
                    bone.matrix_basis=self.arm_entry_basis[bone.name]
            bpy.context.view_layer.update()
        if apply_pelvis:
            if self.fixed_pelvis:
                self._apply_pelvis_transform(requested)
            else:
                self._pelvis(requested)
        chains=sorted({self.controls[id].chain for id in requested if self.controls[id].value_shape=='scalar'},
                      key=lambda id:(sum(1 for _ in self._parents(id)),id))
        for chain in chains:
            if chain in ANGULAR_CHAINS: self._angular(chain,requested)
        for id,orientation in requested.items():
            if not id.endswith('.upper_arm.orientation'):continue
            chain=self.controls[id].chain
            bone=h.rig.pose.bones[self.joints[chain].source_bones[0]]
            world=h.rig.matrix_world @ bone.matrix
            rotation=Quaternion(orientation) @ rp.semantic_frame(h,p,chain).to_quaternion().conjugated() @ world.to_quaternion()
            bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
            bpy.context.view_layer.update()
        if any(id in requested for id in ('head.orientation','head.torso_orientation')):
            # Parent tracks have already been applied. Resolve look-at from this frame's
            # actual head position, using the shared sampler and existing activation bindings.
            current=rp.capture_motion_state(h,p,revision=self.motion.entry_snapshot.revision,captured_time_s=time_s)
            targets=sample_motion(self.motion,time_s,current,self.cursor)
            requested={v.control_id:v.value for v in targets.controls}
            for id in ('head.orientation','head.torso_orientation'):
                if id not in requested: continue
                desired=Quaternion(requested[id])
                if id=='head.torso_orientation':
                    torso=next(j for j in ('spine.upper','spine.mid','torso') if j in self.joints)
                    desired=rp.semantic_frame(h,p,torso).to_quaternion() @ desired
                bone=h.rig.pose.bones[self.joints['head'].source_bones[0]]
                world=h.rig.matrix_world @ bone.matrix
                rotation=desired @ rp.semantic_frame(h,p,'head').to_quaternion().conjugated() @ world.to_quaternion()
                bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
                bpy.context.view_layer.update()
        if self.knee_crawl:
            from .support_mechanics import apply_crawl_knees
            apply_crawl_knees(self, requested, targets.active_contacts, time_s)
        elif p.version in (7,8):
            from .leg_mechanics import apply as apply_legs
            leg_targets=requested
            if p.version==8 and not self.fixed_support:
                from .foot_mechanics import apply_local, apply_pivots
                leg_targets=apply_pivots(self,requested,targets.active_contacts)
            apply_legs(self,leg_targets)
            if p.version==8 and not self.fixed_support: apply_local(self,requested)
        if p.version in (5,6,7,8):
            from .hand_mechanics import apply
            apply(self,requested)
        if p.version in (6,7,8) and 'finger_v1:bind_palm_axes_three_joint_digits' in p.calibration_provenance.evidence:
            from .finger_mechanics import apply as apply_fingers
            apply_fingers(self,requested)
        for value in targets.controls:
            if p.version in (5,6,7,8):continue  # Coordinated endpoint/pole/palm solve above.
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
        fixed_anchors = []
        skin_support = {}
        foot_goals = []
        body_goal = None
        events = targets.active_contacts
        if self.fixed_support:
            events = sorted(events, key=lambda event: (event.anchor_id in BODY_ANCHORS) == self.tracked_body_contact)
        for event in events:
            side=event.anchor_id.split('.')[0]
            position=Vector(rp.measure_endpoint(h,p,event.anchor_id))
            if self.fixed_support:
                acquire = min(1, (time_s - event.interval.start_s) / event.acquire_s) if event.acquire_s else 1
                release = min(1, (event.interval.end_s - time_s) / event.release_s) if event.release_s else 1
                weight = contact_ease(min(acquire, release))
                if event.anchor_id in BODY_ANCHORS:
                    surface = self.fixed_surfaces[event.surface_id]
                    shift = Vector(event.target_world_v1) - position
                    position = body_contact_point(h, p, event.anchor_id, surface, offset_xy=tuple(shift[:2]))
                goal = position.lerp(Vector(event.target_world_v1), weight)
                if self.body_support and not self.tracked_body_contact and event.anchor_id in FOOT_ANCHORS and release < 1:
                    # The new body contact lowers the pelvis. Author a small
                    # released-foot lift instead of dragging its rest pose
                    # through the old surface as the constraint fades.
                    goal = Vector(event.target_world_v1) + Vector((0, 0, .04 * (1 - weight)))
                if event.anchor_id in PALM_ANCHORS and weight > 1e-8:
                    from .support_mechanics import apply_palm
                    goal = apply_palm(self, side, event.target_world_v1, weight)
                elif self.knee_crawl and event.anchor_id in BODY_ANCHORS:
                    if min(acquire, release) >= 1 - 1e-9:
                        errors[event.anchor_id] = (Vector(event.target_world_v1) - position).length
                elif event.anchor_id in BODY_ANCHORS and weight > 1e-8:
                    self._translate_pelvis(goal - position)
                    for foot_event, foot_goal in foot_goals:
                        self._fixed_foot(foot_event, foot_goal)
                    body_goal = (event, goal)
                elif event.anchor_id in FOOT_ANCHORS and (weight > 1e-8 or not self.tracked_body_contact):
                    self._fixed_foot(event, goal)
                    foot_goals.append((event, goal))
                if event.anchor_id not in BODY_ANCHORS:
                    errors[event.anchor_id] = (Vector(rp.measure_endpoint(h,p,event.anchor_id)) - goal).length
                if min(acquire, release) >= 1 - 1e-9:
                    fixed_anchors.append(c.ContactAnchor(event.anchor_id, event.surface_id, event.target_world_v1,
                                                        'world', 'metre'))
                    if event.anchor_id in PALM_ANCHORS + BODY_ANCHORS:
                        skin_support[event.anchor_id] = self.fixed_surfaces[event.surface_id]
                continue
            if p.version==8 and event.anchor_id.endswith('.sole') and event.acquire_s and event.interval.start_s>0:
                if event.event_id not in self.foot_acquisitions:
                    if abs(position.z)>.003:
                        c.fail('ENTRY_MISMATCH','Landing has not reached the floor sole plane',
                               details={'anchor_id':event.anchor_id,'height_m':position.z})
                    self.anchors[event.anchor_id]=position.copy()
                    self.foot_acquisitions.add(event.event_id)
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
                    if self.moves_root:
                        if delta.length > .001:
                            c.fail('CONSTRAINT_CONFLICT', 'Root trajectory moves a locked sole',
                                   details={'anchor_id': event.anchor_id, 'drift_m': delta.length})
                    else:
                        foot=h.bones[side.title()+'Foot']
                        target=foot.head+h.rig.matrix_world.inverted().to_3x3() @ delta
                        orientation=foot.matrix.to_quaternion() if p.version==8 and event.anchor_id.endswith(('.heel','.forefoot')) else self.foot_orientations[side]
                        set_contact(h,ContactConstraint(side+'_foot'),target,orientation,leg_pole=self._leg_pole(side))
                residual=(Vector(rp.measure_endpoint(h,p,event.anchor_id))-anchor).length*weight
                errors[side+'_foot']=max(errors.get(side+'_foot',0),residual) if p.version==8 else residual
        if body_goal is not None:
            event, goal = body_goal
            surface = self.fixed_surfaces[event.surface_id]
            for _ in range(2):
                delta = goal - body_contact_point(h, p, event.anchor_id, surface)
                if delta.length <= .0005:
                    break
                self._translate_pelvis(delta)
                for foot_event, foot_goal in foot_goals:
                    self._fixed_foot(foot_event, foot_goal)
            errors[event.anchor_id] = (goal - body_contact_point(h, p, event.anchor_id, surface)).length
            for foot_event, foot_goal in foot_goals:
                point = Vector(rp.measure_endpoint(h, p, foot_event.anchor_id))
                errors[foot_event.anchor_id] = (foot_goal - point).length
        anchors = tuple(fixed_anchors) if self.fixed_support else tuple(
            c.ContactAnchor(id,'floor',tuple(self.anchors[id]),'world','metre') for id in active)
        active = [anchor.anchor_id for anchor in anchors]
        try:
            solved=rp.capture_motion_state(h,p,revision=self.motion.entry_snapshot.revision,captured_time_s=time_s,
                                          contact_anchors=anchors,active_contacts=tuple(active))
        except c.MotionContractError as error:
            limit = self.limits.get(error.control_id)
            if limit is not None:
                error.details.update(time_s=time_s, measured_deg=rp.measure_joint_angle(h,p,error.control_id),
                                     bounds_deg=(limit.minimum, limit.maximum))
            raise
        measured={v.control_id:v for v in solved.measured_controls}
        violations=[]
        skin_gaps = {}
        if skin_support:
            from .geometry import support_skin_height
            from .support_mechanics import support_part
            for anchor, surface in skin_support.items():
                gap = abs(support_skin_height(h, support_part(anchor), surface) - surface.height)
                if not math.isfinite(gap):
                    c.fail('ENTRY_MISMATCH', 'No contact skin lies over the acquired support surface',
                           details={'anchor_id': anchor})
                skin_gaps[anchor] = gap
                errors[anchor] = max(errors[anchor], gap)
        arm_clearance={};arm_poles={}
        if self.arm_review:
            for side in ('left','right'):
                if not any(id.startswith(side+'.') for id in requested):continue
                clearance=self._arm_clearance(side);arm_clearance[side]=clearance
                if clearance<-.003:violations.append(('body_clearance',side,-clearance,.003))
                pole=Vector(rp.measure_bend_plane(h,p,side+'.forearm'));arm_poles[side]=tuple(pole)
                previous=self.previous_arm_poles.get(side)
                if previous is not None and previous.dot(pole)<0:
                    violations.append(('elbow_pole_flip',side,math.degrees(previous.angle(pole)),90))
                self.previous_arm_poles[side]=pole.copy()
        tracking={}
        review_controls = targets.controls
        if self.tracked_body_contact and body_goal is not None:
            # The approach endpoint remains the deterministic base pose. After
            # acquisition starts, the measured skin contact owns the correction.
            review_controls = tuple(target for target in review_controls if target.control_id != 'pelvis.position')
        for target in review_controls:
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
        if self.arm_review:
            for side in ('left','right'):
                if side+'.hand.position' in requested or side+'.hand.torso_position' in requested or side+'.elbow.flexion' in requested:continue  # Declared coordinated elbow motion.
                if not any(id.startswith(side+'.') for id in requested):continue
                id=side+'.elbow.flexion'
                error=abs(measured[id].value-entry[id].value)
                if error>.5:violations.append(('unrequested_elbow_change',id,error,.5))
        unrelated=0
        if self.moves_root:
            delta_world = h.rig.matrix_world @ self.root_entry.inverted()
            delta_rotation = delta_world.to_quaternion()
            if grounded_articulation:
                pelvis_shift = Vector(measured['pelvis.position'].value) - delta_world @ Vector(entry['pelvis.position'].value)
        for id,value in measured.items():
            control=self.controls[id]
            expected = entry[id].value
            if self.moves_root:
                if id in ROOT_CONTROLS:
                    continue
                if grounded_articulation and (control.chain in LEG_CHAINS or any(parent in LEG_CHAINS for parent in self._parents(control.chain))):
                    continue
                if value.frame == 'world':
                    if control.value_shape == 'quaternion':
                        expected = tuple(delta_rotation @ Quaternion(expected))
                    elif control.value_shape == 'vector':
                        point = (delta_world if control.unit == 'metre' else delta_rotation) @ Vector(expected)
                        if grounded_articulation and control.unit == 'metre':
                            point += pelvis_shift
                        expected = tuple(point)
            elif any(control.chain==owned or owned in tuple(self._parents(control.chain)) for owned in self.owned):
                continue
            error=value_error(value.value,expected,control.value_shape)
            tolerance=.002 if control.unit=='metre' else .5 if control.unit=='degree' or control.value_shape=='quaternion' else .008726535
            unrelated=max(unrelated,error)
            if error>tolerance: violations.append(('unrelated_change',id,error,tolerance))
        # Unowned angular components on an owned head/spine chain are explicit locks.
        for id,value in measured.items():
            if id in requested or self.controls[id].chain not in ANGULAR_CHAINS: continue
            if self.controls[id].chain=='head' and any(key in requested for key in ('head.orientation','head.torso_orientation')): continue
            if self.controls[id].value_shape!='scalar': continue
            error=value_error(value.value,entry[id].value,self.controls[id].value_shape)
            if error>.5: violations.append(('unrelated_change',id,error,.5))
        sample=capture_sample(h,frame,','.join(targets.source_instance_ids),errors)
        if self.moves_root or self.fixed_support:
            from .geometry import seat_penetration
            sample['surfaces'] = {surface.name: seat_penetration(h, surface)
                                  for surface in h.surfaces if surface.name != 'floor' and surface.size}
        if self.moves_root:
            sample['rotations']['object_root'] = h.rig.matrix_world.to_quaternion()
        if p.version in (6,7,8) and 'finger_v1:bind_palm_axes_three_joint_digits' in p.calibration_provenance.evidence:
            # Extend the existing whole-motion speed/acceleration reviewer with
            # actual digit rotations; the core avatar map deliberately omits them.
            for chain,mapping in self.joints.items():
                if '.finger.' in chain:
                    sample['rotations'][chain]=(h.rig.matrix_world @ h.rig.pose.bones[mapping.source_bones[0]].matrix).to_quaternion()
        sample['controls']={v.control_id:v.value for v in solved.measured_controls}
        leg_clearance=None
        if p.version in (7,8) and any('.hip.' in key or '.knee.' in key or '.foot.' in key or key=='pelvis.position' for key in requested):
            from .leg_mechanics import clearance
            leg_clearance=clearance(self)
            if leg_clearance<-.003:violations.append(('leg_clearance','legs',-leg_clearance,.003))
        sample['semantic_violations']=violations
        details={'frame':frame,'time_s':time_s,'source_instance_ids':list(targets.source_instance_ids),
            'targets':{v.control_id:v.value for v in review_controls},'measured':sample['controls'],
            'checked_goal_ids':[g.goal_id for g in targets.expected_goals],
            'tracking_errors':tracking,'contacts':dict(errors),'floor_m':sample['floor'],'violations':violations}
        if p.version in (6,7,8) and 'finger_v1:bind_palm_axes_three_joint_digits' in p.calibration_provenance.evidence:
            details['finger_rotations']={key:tuple(q) for key,q in sample['rotations'].items() if '.finger.' in key}
            details['finger_tips']={key:tuple(h.rig.matrix_world @ h.rig.pose.bones[mapping.source_bones[0]].tail)
                for key,mapping in self.joints.items() if '.finger.' in key and key.endswith('.3')}
        if self.arm_review:details.update({'arm_clearance_m':arm_clearance,'elbow_poles':arm_poles})
        if p.version in (7,8):
            details['leg_clearance_m']=leg_clearance
            details['leg_points']={side:[tuple(h.rig.matrix_world @ h.bones[side.title()+part].head)
                for part in ('UpLeg','Leg','Foot')] for side in ('left','right')}
        if p.version==8:
            details['active_foot_anchors']={anchor.anchor_id:anchor.position for anchor in anchors
                                            if anchor.anchor_id in FOOT_ANCHORS}
        if skin_gaps:
            details['support_skin_gaps_m'] = skin_gaps
        if self.fixed_support and any(event.anchor_id in PALM_ANCHORS + BODY_ANCHORS for event in self.motion.contact_events):
            details['active_support_anchors'] = {anchor.anchor_id: c.to_dict(anchor) for anchor in anchors}
        if self.balance_track is not None:
            side = anchors[0].anchor_id.split('.')[0]
            other = 'right' if side == 'left' else 'left'
            heel, forefoot = (measured[f'{side}.{part}.position'].value for part in ('heel', 'forefoot'))
            center = measured['pelvis.position'].value
            margin = sole_region_margin(center, heel, forefoot)
            settled = time_s >= self.balance_track.interval.end_s - 1e-9
            clearance = measured[f'{other}.sole.position'].value[2]
            if settled and margin < 0:
                violations.append(('geometric_balance', 'pelvis', -margin, 0))
            if clearance < .02:
                violations.append(('free_sole_clearance', other, .02 - clearance, 0))
            details['geometric_balance'] = {'pelvis_projection_xy_m': center[:2], 'margin_m': margin,
                                            'settled': settled, 'free_sole_clearance_m': clearance}
        if self.moves_root:
            details['root_support'] = 'grounded' if active else 'airborne'
            details['unrelated_error_max'] = unrelated
        self.diagnostics.append(details)
        sample['semantic_details']=details
        sample['snapshot']=solved
        self.measured=solved
        if not self.fixed_support:
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
