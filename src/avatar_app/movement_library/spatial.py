"""Small pure quaternion/vector operations in the calibrated +X/+Y/+Z convention."""
import math
from . import contracts as c


def normalize(v):
    length=math.sqrt(sum(x*x for x in v))
    if length<1e-9: c.fail('INVALID_PARAMETER','Direction/rotation is singular')
    return tuple(x/length for x in v)


def multiply(a,b):
    w,x,y,z=a; v,i,j,k=b
    return (w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v)


def inverse(q): return (q[0],-q[1],-q[2],-q[3])


def rotate(q,v): return multiply(multiply(q,(0,*v)),inverse(q))[1:]


def angle_rotation(pitch=0,yaw=0,roll=0):
    # Inverse of the three orthogonal signed swing/twist projections, not Euler angles.
    return normalize((1,-math.tan(math.radians(pitch)/2),math.tan(math.radians(roll)/2),math.tan(math.radians(yaw)/2)))


def projected_angles(q):
    if q[0]<0: q=tuple(-v for v in q)
    return dict(pitch=math.degrees(2*math.atan2(-q[1],q[0])),
                yaw=math.degrees(2*math.atan2(q[3],q[0])),roll=math.degrees(2*math.atan2(q[2],q[0])))


def look_rotation(position,target):
    """World orientation: +Y aims at the point, +Z stays as near world-up as possible."""
    y=normalize(tuple(b-a for a,b in zip(position,target)))
    x=(y[1],-y[0],0)
    if sum(v*v for v in x)<1e-8:
        c.fail('INVALID_PARAMETER','Look target is too close to the vertical roll singularity')
    x=normalize(x)
    z=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])
    return _frame_rotation(x,y,z)


def palm_rotation(finger_forward,palm_normal):
    """Hard orthogonal +Y finger and +Z palm targets, in one declared frame."""
    y=normalize(finger_forward);z=normalize(palm_normal)
    if abs(sum(a*b for a,b in zip(y,z)))>1e-6:
        c.fail('CONSTRAINT_CONFLICT','Finger-forward and palm-normal targets must be perpendicular')
    x=(y[1]*z[2]-y[2]*z[1],y[2]*z[0]-y[0]*z[2],y[0]*z[1]-y[1]*z[0])
    return _frame_rotation(x,y,z)


def _frame_rotation(x,y,z):
    rows=tuple(tuple(column[i] for column in (x,y,z)) for i in range(3))
    # Stable matrix-to-quaternion conversion, including targets behind the world axes.
    trace=sum(rows[i][i] for i in range(3))
    if trace>0:
        s=math.sqrt(trace+1)*2
        return normalize((s/4,(rows[2][1]-rows[1][2])/s,(rows[0][2]-rows[2][0])/s,(rows[1][0]-rows[0][1])/s))
    i=max(range(3),key=lambda i:rows[i][i]); j=(i+1)%3; k=(i+2)%3
    s=math.sqrt(1+rows[i][i]-rows[j][j]-rows[k][k])*2
    q=[(rows[k][j]-rows[j][k])/s,0,0,0]
    q[i+1]=s/4; q[j+1]=(rows[j][i]+rows[i][j])/s; q[k+1]=(rows[k][i]+rows[i][k])/s
    return normalize(tuple(q))


def with_head_aim_v1(profile):
    """Opt-in profile v2 extension; v1 calibration and saved fixtures stay unchanged."""
    from dataclasses import replace
    if any(v.id=='head.orientation' for v in profile.controls): return profile
    if profile.version!=1: c.fail('VERSION_MISMATCH','Head-aim extension requires calibration v1 or its v2 extension')
    if not any(v.semantic_id=='head' for v in profile.rest_to_semantic_mappings):
        c.fail('MISSING_CAPABILITY','Head aim requires an actual calibrated head')
    extra=(c.ControlSpec('head.position','metre','vector',3,('world',),'head','measure.head.position'),
           c.ControlSpec('head.orientation','unitless','quaternion',4,('world',),'head','measure.head.orientation'),
           c.ControlSpec('head.torso_orientation','unitless','quaternion',4,('current_torso',),'head','measure.head.torso_orientation'))
    evidence=profile.calibration_provenance.evidence+('head_aim_v1:world_position_world_and_torso_orientation',)
    return replace(profile,version=2,controls=profile.controls+extra,
                   capabilities=tuple(sorted((*profile.capabilities,*(v.capability for v in extra)))),
                   calibration_provenance=replace(profile.calibration_provenance,evidence=evidence))
