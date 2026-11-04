"""Opt-in profile 6: existing three-joint digits, never invented anatomy."""
from dataclasses import replace
from . import contracts as c
from .hands import with_hands_v1
from .joints import _enum, _number, _path, _fragment, _seconds
from .spatial import normalize

IDS=('hand.gesture','finger.curl_spread')
DIGITS=('thumb','index','middle','ring','pinky')
MARKER='finger_v1:bind_palm_axes_three_joint_digits'
CURL_MAX={'thumb':65,'index':90,'middle':90,'ring':90,'pinky':90}


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def with_fingers_v1(profile):
    """Calibrate from existing rest landmarks; parent/chain validity is required.

    Curl bends toward the palm; positive spread bends toward the thumb side.
    Thumb is a documented hinge approximation, not an opposition/grasp solver.
    """
    if profile.version==6 and MARKER in profile.calibration_provenance.evidence:return profile
    p=with_hands_v1(profile);joints={j.semantic_id:j for j in p.rest_to_semantic_mappings}
    landmarks={x.id:x.position for x in p.landmarks};controls=[];limits=[];caps=[]
    for side,other in (('left','right'),('right','left')):
        for digit in DIGITS:
            base=side+'.finger.'+digit;chains=[base+'.'+str(i) for i in (1,2,3)]
            if (not all(x in joints for x in chains) or joints[chains[0]].parent_id!=side+'.wrist'
                or any(joints[b].parent_id!=a for a,b in zip(chains,chains[1:]))
                or side+'.palm.normal' not in landmarks):continue
            normal=normalize(landmarks[side+'.palm.normal']);radial=normalize(landmarks[side+'.palm.radial'])
            for index,chain in enumerate(chains,1):
                direction=normalize(landmarks[chain+'.tip'])
                curl=normalize(_cross(direction,normal))
                # Orthogonal independent axes. Sign is anatomical, not rig-local XYZ.
                spread=normalize(_cross(curl,direction))
                if sum(a*b for a,b in zip(_cross(spread,direction),radial))<0:spread=tuple(-x for x in spread)
                for name,axis,lo,hi in (('curl',curl,-10,CURL_MAX[digit]+10),
                                       ('spread',spread,-20 if digit=='thumb' else -25,20 if digit=='thumb' else 25)):
                    if name=='spread' and index!=1:continue
                    key=chain+'.'+name;frame='joint:'+joints[chain].parent_id
                    controls.append(c.ControlSpec(key,'degree','scalar',1,(frame,),chain,'measure.'+key))
                    limits.append(c.JointLimit(key,lo,hi,0,axis,None,1,
                        'bind-calibrated parent-relative swing/twist projection; thumb hinge approximation',lo,hi))
                    caps.append('measure.'+key)
            caps.extend(('detail.'+base+'.mapped_three_joint', 'detail.'+base+'.'+('approximate_thumb_hinge' if digit=='thumb' else 'calibrated_curl_spread')))
    return replace(p,version=6,controls=p.controls+tuple(controls),joint_limits=p.joint_limits+tuple(limits),
        capabilities=tuple(sorted(set((*p.capabilities,*caps)))),calibration_provenance=replace(p.calibration_provenance,
        evidence=p.calibration_provenance.evidence+(MARKER,)))


def selected_digits(parameters):
    selection=parameters['selection']
    return DIGITS if selection=='all' else DIGITS[1:] if selection=='four_fingers' else (selection,)


def build(instance,entry,profile,surfaces):
    if profile.version not in (6,7) or MARKER not in profile.calibration_provenance.evidence:
        c.fail('MISSING_CAPABILITY','Finger detail requires calibrated profile 6')
    p={x.name:x.value for x in instance.parameters};values={x.control_id:x.value for x in entry.measured_controls}
    sides=('left','right') if p['side']=='both' else (p['side'],)
    digits=DIGITS if instance.definition_id=='hand.gesture' else selected_digits(p)
    missing=[side+'.finger.'+digit for side in sides for digit in digits
             if not all(side+'.finger.'+digit+'.'+str(i)+'.curl' in values for i in (1,2,3))
             or side+'.finger.'+digit+'.1.spread' not in values]
    if missing:c.fail('MISSING_CAPABILITY','Requested finger detail unavailable; major arm motion is independent',
                      details={'missing':missing,'omitted_detail':instance.definition_id})
    paths={};d=_seconds(p['duration_s']);hold=_seconds(p['hold_s']);end=0
    for side in sides:
        for digit in digits:
            if instance.definition_id=='hand.gesture':
                gesture=p['gesture'];curl=0 if gesture=='open' or gesture=='point' and digit=='index' else .18 if gesture=='relaxed' else .72
                spread=0
            else:
                curl=p.get(digit+'_curl') if p.get(digit+'_curl') is not None else p['curl']
                spread=p.get(digit+'_spread_deg') if p.get(digit+'_spread_deg') is not None else p['spread_deg']
            for i in (1,2,3):
                key=side+'.finger.'+digit+'.'+str(i)+'.curl'
                limit=next(x for x in profile.joint_limits if x.control_id==key)
                paths[key],end=_path(values[key],[curl*CURL_MAX[digit]],d,hold,p['return_policy'])
            key=side+'.finger.'+digit+'.1.spread'
            limit=next(x for x in profile.joint_limits if x.control_id==key)
            bound=15 if digit=='thumb' else 20
            if not -bound<=spread<=bound:c.fail('INVALID_PARAMETER','Selected digit spread exceeds calibrated movement bound',control_id=key)
            paths[key],end=_path(values[key],[spread],d,hold,p['return_policy'])
    if instance.definition_id=='finger.curl_spread':
        inactive=[name for digit in DIGITS if digit not in digits for name in (digit+'_curl',digit+'_spread_deg') if p[name] is not None]
        if inactive:c.fail('INVALID_PARAMETER','Override names an unselected digit',details={'parameters':inactive})
    return _fragment(instance,entry,profile,paths,end,(c.PhaseLandmark('arrival',d),c.PhaseLandmark('end',end)))


BUILDERS={'fingers.targets.v1':build}


def register_fingers(catalog,profile):
    from .registry import register_movement
    if profile.version not in (6,7) or MARKER not in profile.calibration_provenance.evidence:return catalog
    for id in IDS:
        common=(_enum('side','left',('left','right','both')),_number('duration_s','second',1.5,1.5,3),
                _number('hold_s','second',.1,0,1),_enum('return_policy','return_to_entry',('return_to_entry','preserve_end')))
        if id=='hand.gesture':params=(_enum('gesture','relaxed',('open','relaxed','fist','point')),)+common
        else:
            params=(_enum('selection','all',('all','four_fingers',*DIGITS)),_number('curl','unitless',.25,0,1),
                    _number('spread_deg','degree',0,-20,20))+common
            params+=tuple(replace(_number(digit+suffix,unit,0,lo,hi),nullable=True,default=None)
                for digit in DIGITS for suffix,unit,lo,hi in (('_curl','unitless',0,1),('_spread_deg','degree',-20,20)))
        chains=tuple(sorted({control.chain for control in profile.controls if '.finger.' in control.id}))
        # Missing chains are checked after explicit side/digit selection, never faked.
        register_movement(c.MovementDefinition(id,1,'joint','Optional calibrated finger detail; thumb hinge approximation',
            params,(),(),chains,(),(),'fingers.targets.v1',('finger_detail','no_grasp_solver'),('arrival','end'),'return_to_entry'),catalog)
    return catalog
