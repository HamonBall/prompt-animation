"""Bounded deterministic geometric chords shared by limb builders."""
import math
from . import contracts as c
from .spatial import normalize


def axis_rotation(axis,degrees):
    axis=normalize(axis)
    if not math.isfinite(degrees) or abs(degrees)>360:c.fail('INVALID_PARAMETER','Rotation exceeds one bounded cycle')
    a=math.radians(degrees)/2
    return (math.cos(a),*(v*math.sin(a) for v in axis))


def tangent_rotation_axes(direction,outward,preferred_forward):
    """Outward and forward rotation axes at a captured segment direction.

    Projection handles overhead arms as well as lowered arms. At a parallel
    reference, use the next fixed world axis to choose a deterministic plane.
    """
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    w=normalize(direction);references=(preferred_forward,(0,0,1),(1,0,0),(0,1,0))
    u=tuple(a-dot(outward,w)*b for a,b in zip(outward,w))
    if dot(u,u)<1e-12:
        for reference in references:
            u=tuple(a-dot(reference,w)*b for a,b in zip(reference,w))
            if dot(u,u)>=1e-12:break
    u=normalize(u);v=normalize(cross(w,u))
    for reference in references:
        projection=dot(v,reference)
        if abs(projection)>1e-6:
            if projection<0:v=tuple(-x for x in v)
            break
    return normalize(cross(w,u)),normalize(cross(w,v))


def segment_distance(a,b,c0,d):
    """Closest distance between two bounded line segments, including parallels."""
    def dot(x,y):return sum(i*j for i,j in zip(x,y))
    def sub(x,y):return tuple(i-j for i,j in zip(x,y))
    def clamp(x):return max(0,min(1,x))
    u,v,w=sub(b,a),sub(d,c0),sub(a,c0)
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    if aa<1e-12 and cc<1e-12:s=t=0
    elif aa<1e-12:s=0;t=clamp(ee/cc)
    elif cc<1e-12:t=0;s=clamp(-dd/aa)
    else:
        denominator=aa*cc-bb*bb
        s=clamp((bb*ee-cc*dd)/denominator) if denominator>1e-12*aa*cc else 0
        t=(bb*s+ee)/cc
        if t<0:t=0;s=clamp(-dd/aa)
        elif t>1:t=1;s=clamp((bb-dd)/aa)
    return math.sqrt(sum((w[i]+s*u[i]-t*v[i])**2 for i in range(3)))


def line(start,end,steps=1):
    if type(steps) is not int or not 1<=steps<=64:c.fail('RESOURCE_LIMIT','Curve needs 1..64 chords')
    if len(start)!=3 or len(end)!=3 or not all(math.isfinite(v) and abs(v)<=20 for v in (*start,*end)):
        c.fail('INVALID_PARAMETER','Curve positions must be finite world metres within 20m')
    return tuple(tuple(a+(b-a)*i/steps for a,b in zip(start,end)) for i in range(steps+1))


def arc(center,u,v,radius,*,start_degrees=0,sweep_degrees=360,steps=32,phase_easing='linear'):
    line(center,center,steps)
    if not all(math.isfinite(a) for a in (radius,start_degrees,sweep_degrees)) or not 0<=radius<=1 or abs(sweep_degrees)>360:
        c.fail('INVALID_PARAMETER','Arc radius must be 0..1m and sweep at most 360 degrees')
    u=normalize(u);v=normalize(v)
    if abs(sum(a*b for a,b in zip(u,v)))>1e-6:c.fail('INVALID_PARAMETER','Arc basis must be orthogonal')
    if phase_easing not in ('linear','smooth'):c.fail('INVALID_PARAMETER','Unknown arc phase easing')
    def phase(i):
        t=i/steps
        return t*t*(3-2*t) if phase_easing=='smooth' else t
    points=tuple(tuple(center[j]+radius*(u[j]*math.cos(math.radians(start_degrees+sweep_degrees*phase(i)))+
                 v[j]*math.sin(math.radians(start_degrees+sweep_degrees*phase(i)))) for j in range(3)) for i in range(steps+1))
    if abs(sweep_degrees)==360:points=points[:-1]+(points[0],)
    for point in points:line(point,point)
    return points
