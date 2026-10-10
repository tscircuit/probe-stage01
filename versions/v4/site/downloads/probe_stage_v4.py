"""build123d public v4: broad-saddle, rear-controller-clear, 40 mm vertical-travel microscope probe mechanism.

Millimetres. Local wheel plane XY, axle +Z; drive plane yawed 0 degrees around world Y.
The slide moves vertically. Only the probe/collet is tilted at 60 degrees
above the specimen plate. Barrel bottom is world Y=0, barrel body extends +Y.
Specimen is Y=-100 mm. A long straight reference probe is held externally,
with only its 1 mm metal stem within the central optical projection. The
outboard 6 mm shank fits a 6 mm collet. Full travel is also checked using the
conservative envelope of a 6 mm shaft along the entire length.

Compact v4 uses a radial drive plane with the motor rear pointing tangentially away from the barrel, a 96 mm wheel, spoke openings,
a ribbed perimeter frame and a broad continuous clamp-to-frame saddle. This is a dimensional
mechanical prototype, not a load-rated assembly; ribs have no FEA rating.
Use a smooth Ø5 mm running section at each bearing inner race, with M5
threads outside the races. Standard Ø6 mm shoulder bolts do not fit these
bearings. Generic NEMA17 face uses M3 screws; principal other hardware is M5.
STL files retain assembly placement; arrange orientation for manufacture.
"""
from __future__ import annotations
import argparse, hashlib, json, math, shutil
from dataclasses import dataclass, asdict
from pathlib import Path
import build123d as b

@dataclass
class Parameters:
    microscope_d: float = 44.0
    clamp_clearance: float = 0.4
    clamp_outer_r: float = 29.0
    clamp_y: float = 9.0
    clamp_width: float = 18.0
    split_gap: float = 0.8
    stroke: float = 40.0
    crank_r: float = 22.5
    rod_length: float = 88.0
    module: float = 1.0
    ring_teeth: int = 80
    pinion_teeth: int = 20
    pressure_angle: float = 20.0
    backlash: float = 0.2
    wheel_r: float = 48.0
    window_inner_r: float = 16.0
    wheel_thickness: float = 6.0
    bearing_id: float = 5.0
    bearing_od: float = 16.0
    bearing_width: float = 5.0
    bearing_seat_allowance: float = 0.10
    m5_clearance: float = 5.3
    motor_size: float = 42.0
    motor_length: float = 40.0
    controller_depth: float = 20.0
    controller_clearance: float = 2.0
    motor_hole_spacing: float = 31.0
    motor_shaft_d: float = 5.0
    probe_d: float = 6.0
    probe_clearance: float = 0.35
    probe_x: float = -31.0
    probe_z: float = -25.5
    probe_tip_extension: float = 90.0  # tip to external collet mid-plane
    probe_total_length: float = 104.0
    probe_stem_d: float = 1.0
    probe_stem_length: float = 60.0
    probe_transition_length: float = 10.0
    slide_clearance: float = 0.30
    approach_angle_degrees: float = 60.0
    working_distance: float = 100.0
    clamp_rotation_degrees: float = -45.0  # ears clear the probe plane and strut root
    frame_thickness: float = 5.0
    strut_width: float = 8.0
    strut_depth: float = 6.0
    saddle_thickness: float = 9.5
    saddle_corner_radius: float = 2.5
    drive_yaw_degrees: float = 0.0
    stop_radius: float = 44.0

    @property
    def ring_pitch_r(self): return self.module*self.ring_teeth/2
    @property
    def pinion_pitch_r(self): return self.module*self.pinion_teeth/2
    @property
    def motor_offset(self): return self.ring_pitch_r-self.pinion_pitch_r
    @property
    def limit(self): return math.degrees(math.asin(self.stroke/(2*self.crank_r)))
    @property
    def tilt(self): return 0.0
    @property
    def target_y_local(self): return kinematics(-self.limit,self)[2]-self.probe_tip_extension*math.sin(math.radians(self.approach_angle_degrees))
    @property
    def world_origin(self):
        return (76.0,-self.working_distance-self.target_y_local,25.5)
    @property
    def probe_axis(self):
        a=math.radians(self.approach_angle_degrees);yaw=math.radians(self.drive_yaw_degrees)
        return (math.cos(a)*math.cos(yaw),math.sin(a),math.cos(a)*math.sin(yaw))
    @property
    def pinch_center(self):
        return (self.probe_x,0.0,self.probe_z+6)

P=Parameters()

def to_world(shape,p=P): return b.Pos(*p.world_origin)*b.Rotation(0,p.drive_yaw_degrees,0)*shape
def to_local(shape,p=P): return b.Rotation(0,-p.drive_yaw_degrees,0)*b.Pos(*[-v for v in p.world_origin])*shape
def local_point(world,p=P):
    o=p.world_origin;a=math.radians(-p.drive_yaw_degrees)
    dx,dy,dz=[world[i]-o[i] for i in range(3)]
    return dx*math.cos(a)+dz*math.sin(a),dy,-dx*math.sin(a)+dz*math.cos(a)

def box(x0,x1,y0,y1,z0,z1):
    return b.Solid.make_box(x1-x0,y1-y0,z1-z0,b.Plane(origin=(x0,y0,z0)))
def cylinder(r,h,origin=(0,0,0),axis=(0,0,1)):
    return b.Solid.make_cylinder(r,h,b.Plane(origin=origin,z_dir=axis))
def polygon_prism(points,z,thickness):
    return b.Solid.extrude(b.Face(b.Wire.make_polygon([(x,y,z) for x,y in points],close=True)),(0,0,thickness))
def beam(a,c,width,z0,z1,round_ends=True):
    dx,dy=c[0]-a[0],c[1]-a[1]; length=math.hypot(dx,dy)
    nx,ny=-dy/length*width/2,dx/length*width/2
    shape=polygon_prism([(a[0]+nx,a[1]+ny),(c[0]+nx,c[1]+ny),(c[0]-nx,c[1]-ny),(a[0]-nx,a[1]-ny)],z0,z1-z0)
    return shape.fuse(cylinder(width/2,z1-z0,(*a,z0)),cylinder(width/2,z1-z0,(*c,z0))) if round_ends else shape
def hex_prism(af,z,h,x=0,y=0):
    r=af/math.sqrt(3)
    return polygon_prism([(x+r*math.cos(math.radians(30+60*i)),y+r*math.sin(math.radians(30+60*i))) for i in range(6)],z,h)
def polar(r,a): return r*math.cos(a),r*math.sin(a)
def linspace(a,c,n): return [a+(c-a)*i/(n-1) for i in range(n)]
def inv(r,rb):
    t=math.sqrt(max(0,(r/rb)**2-1)); return t-math.atan(t)
def deduplicate(pts):
    out=[]
    for pt in pts:
        if not out or math.dist(pt,out[-1])>1e-8: out.append(pt)
    if len(out)>1 and math.dist(out[0],out[-1])<1e-8: out.pop()
    return out

def involute_pinion(p=P):
    rp=p.pinion_pitch_r; rb=rp*math.cos(math.radians(p.pressure_angle))
    root=rp-1.25*p.module; tip=rp+p.module
    half=math.pi/(2*p.pinion_teeth)-p.backlash/(4*rp)
    def flank(r): return half+inv(rp,rb)-inv(max(r,rb),rb)
    pts=[]; pitch=2*math.pi/p.pinion_teeth
    for k in range(p.pinion_teeth):
        c=k*pitch; ar=flank(root)
        pts += [polar(root,a) for a in linspace(c-pitch/2,c-ar,3)]
        pts += [polar(r,c-flank(r)) for r in [root]+linspace(rb,tip,5)]
        pts += [polar(tip,a) for a in linspace(c-flank(tip),c+flank(tip),3)[1:]]
        pts += [polar(r,c+flank(r)) for r in linspace(tip,rb,5)[1:]+[root]]
        pts += [polar(root,a) for a in linspace(c+ar,c+pitch/2,3)[1:]]
    gear=polygon_prism(deduplicate(pts),8,p.wheel_thickness).fuse(cylinder(8.5,3.5,(0,0,4.5)))
    shaft=cylinder(p.motor_shaft_d/2+0.075,14,(0,0,4)).cut(box(-5,-2.05,-5,5,3,19))
    return gear.cut(shaft).cut(cylinder(1.25,8,(-9,0,6.25),(1,0,0)))

def semicircle_window(p=P):
    rp=p.ring_pitch_r; rb=rp*math.cos(math.radians(p.pressure_angle))
    root=rp+1.25*p.module; tip=rp-p.module
    half=math.pi/(2*p.ring_teeth)-p.backlash/(4*rp)
    def flank(r): return half+inv(r,rb)-inv(rp,rb)
    start=math.pi/2; end=3*math.pi/2; pitch=2*math.pi/p.ring_teeth
    pts=[polar(root,start)]; last=start
    for k in range(p.ring_teeth//2):
        c=start+(k+0.5)*pitch
        pts += [polar(root,a) for a in linspace(last,c-flank(root),2)[1:]]
        pts += [polar(r,c-flank(r)) for r in linspace(root,tip,5)[1:]]
        pts += [polar(tip,a) for a in linspace(c-flank(tip),c+flank(tip),3)[1:]]
        pts += [polar(r,c+flank(r)) for r in linspace(tip,root,5)[1:]]
        last=c+flank(root)
    pts += [polar(root,a) for a in linspace(last,end,2)[1:]]
    pts += [polar(p.window_inner_r,a) for a in linspace(end,start,65)]
    return polygon_prism(deduplicate(pts),7,p.wheel_thickness+2)

def sector_wheel(p=P):
    wheel=cylinder(p.wheel_r,p.wheel_thickness,(0,0,8)).cut(semicircle_window(p))
    # Two bounded spoke openings retain the right-hand crank spoke and rim.
    for aa,bb in [(25,75),(-75,-25)]:
        pts=[polar(34,math.radians(t)) for t in linspace(aa,bb,20)]
        pts += [polar(15,math.radians(t)) for t in linspace(bb,aa,20)]
        wheel=wheel.cut(polygon_prism(pts,7,p.wheel_thickness+2))
    wheel=wheel.fuse(cylinder(11,12,(0,0,6))).cut(cylinder(3.7,14,(0,0,5)))
    seat=(p.bearing_od+p.bearing_seat_allowance)/2
    wheel=wheel.cut(cylinder(seat,5.05,(0,0,5.99))).cut(cylinder(seat,5.05,(0,0,12.99)))
    wheel=wheel.cut(cylinder(p.m5_clearance/2,10,(p.crank_r,0,7)))
    wheel=wheel.cut(cylinder(4.35,2.1,(p.crank_r,0,5.95)))
    return wheel.fuse(cylinder(3.5,3.5,(p.stop_radius,0,4.5)))

BRIDGE_POINTS=[(0,56),(-44,-36)]

def beam3d_world(a,c,width,depth):
    av=b.Vector(a);cv=b.Vector(c);u=(cv-av).normalized()
    v=b.Vector(0,0,1);v=(v-u*v.dot(u)).normalized();w=u.cross(v)
    o=av-v*(width/2)-w*(depth/2)
    return b.Solid.make_box(width,depth,(cv-av).length,b.Plane(origin=o,x_dir=v,z_dir=u))

def clamp_half(front,p=P):
    world=cylinder(p.clamp_outer_r,p.clamp_width,(0,0,0),(0,1,0))
    world=world.cut(cylinder((p.microscope_d+p.clamp_clearance)/2,p.clamp_width+2,(0,-1,0),(0,1,0)))
    world=world.intersect(box(-36,36,-1,19,p.split_gap/2,31) if front else box(-36,36,-1,19,-31,-p.split_gap/2))
    for dx in (-28,28):
        world=world.fuse(box(dx-6,dx+6,0,18,p.split_gap/2,12) if front else box(dx-6,dx+6,0,18,-12,-p.split_gap/2))
        world=world.cut(cylinder(p.m5_clearance/2,30,(dx,p.clamp_y,-14)))
        if front: world=world.cut(cylinder(4.5,5.1,(dx,p.clamp_y,11.95)))
        else: world=world.cut(hex_prism(8.3,-12.01,4.1,dx,p.clamp_y))
    return to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*world,p)

def front_frame(p=P):
    # Thin perimeter rim, local load paths and motor pad replace a solid disc.
    frame=cylinder(56,5,(0,0,-4)).cut(cylinder(52,7,(0,0,-5)))
    frame=frame.fuse(box(-54,-6,-24,24,-4,2),cylinder(14,8,(0,0,-4)),box(-15,15,-136,0,-4,1))
    frame=frame.fuse(beam((0,0),(0,56),10,-4,2,False))
    # Captured 80 mm dovetail with two longitudinal stiffening edge ribs.
    cross=[(-7,.5),(7,.5),(7,6),(11,12),(-11,12),(-7,6)]
    face=b.Face(b.Wire.make_polygon([(x,-130,z) for x,z in cross],close=True))
    frame=frame.fuse(b.Solid.extrude(face,(0,80,0)))
    for x0,x1 in [(-15,-12.5),(12.5,15)]:
        frame=frame.fuse(box(x0,x1,-130,-44,1,5))
    for x0,x1 in [(-12.5,-7.5),(7.5,12.5)]:
        frame=frame.cut(box(x0,x1,-126,-60,-5,1.01))
    delta=math.degrees(2*math.asin(6/(2*p.stop_radius)))
    for sign in (-1,1):
        sx,sy=polar(p.stop_radius,math.radians(sign*(p.limit+delta)))
        if sign==1: frame=frame.fuse(beam((0,0),(sx,sy),10,-4,2,False))
        frame=frame.fuse(cylinder(7,8,(sx,sy,-4)))
    for x,y in BRIDGE_POINTS: frame=frame.fuse(cylinder(6.5,24,(x,y,-4)))
    # A continuous deep saddle replaces the two narrow diagonal braces.
    # Its root overlaps the front clamp over the full 18 mm band, with a
    # flared load path into the rim and motor pad. The lower edge stays inboard
    # of the external probe collet through its complete vertical travel.
    # This geometry improves section area; it carries no tested load rating.
    root_outline=[(11,0),(23,0),(36,42),(62,75),(64,83),
                  (54,82),(30,57),(13,18)]
    root_face=b.Face(b.Wire.make_polygon([(x,y,22) for x,y in root_outline],close=True))
    root_face=root_face.fillet_2d(p.saddle_corner_radius,root_face.vertices())
    saddle=b.Solid.extrude(root_face,(0,0,p.saddle_thickness))
    frame=frame.fuse(to_local(saddle,p))
    frame=frame.fuse(clamp_half(True,p))
    # Preserve the full split gap around rear ear corners for clamp closure.
    # An expanded rear-half bounding box clips only encroaching brace edges.
    relief=box(-34-p.split_gap,34+p.split_gap,-p.split_gap,p.clamp_width+p.split_gap,-p.clamp_outer_r-p.split_gap,p.split_gap/2)
    frame=frame.cut(to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*relief,p))
    frame=frame.cut(to_local(cylinder((p.microscope_d+p.clamp_clearance)/2,20,(0,-1,0),(0,1,0)),p))
    for dx in (-28,28):
        frame=frame.cut(to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*cylinder(p.m5_clearance/2,40,(dx,p.clamp_y,-20)),p))
        # Reapply the complete clamp-head recess after joining the saddle.
        # The head remains accessible rather than embedded in the new root.
        frame=frame.cut(to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*cylinder(4.5,5.1,(dx,p.clamp_y,11.95)),p))
    for x,y in BRIDGE_POINTS:
        frame=frame.cut(cylinder(p.m5_clearance/2,38,(x,y,-10))).cut(hex_prism(8.3,-4.01,4.1,x,y))
    frame=frame.cut(cylinder(11.2,16,(-p.motor_offset,0,-5)))
    for dx in (-p.motor_hole_spacing/2,p.motor_hole_spacing/2):
        for dy in (-p.motor_hole_spacing/2,p.motor_hole_spacing/2):
            frame=frame.cut(cylinder(1.7,10,(-p.motor_offset+dx,dy,-5)))
            frame=frame.cut(cylinder(3.2,3.1,(-p.motor_offset+dx,dy,1)))
    frame=frame.cut(cylinder(p.m5_clearance/2,10,(0,0,-5))).cut(hex_prism(8.3,-4.01,4.1))
    for sign in (-1,1):
        sx,sy=polar(p.stop_radius,math.radians(sign*(p.limit+delta)))
        frame=frame.cut(cylinder(p.m5_clearance/2,10,(sx,sy,-5))).cut(hex_prism(8.3,-.01,4.1,sx,sy))
    return frame

def front_axle_bridge(p=P):
    bridge=cylinder(9,5,(0,0,20))
    for x,y in BRIDGE_POINTS:
        bridge=bridge.fuse(beam((0,0),(x,y),12,20,25)).cut(cylinder(p.m5_clearance/2,7,(x,y,19)))
    return bridge.cut(cylinder(p.m5_clearance/2,7,(0,0,19)))

def connecting_rod(p=P):
    rod=box(-5,5,-p.rod_length,0,30,37)
    for y in (0,-p.rod_length):
        rod=rod.fuse(cylinder(11,7,(0,y,30))).cut(cylinder(3.7,9,(0,y,29)))
        rod=rod.cut(cylinder((p.bearing_od+p.bearing_seat_allowance)/2,5.05,(0,y,29.99)))
    return rod

def probe_carriage(p=P):
    c=box(-15,15,-14,14,6.5,26.5)
    d=p.slide_clearance;top=11+d+(2/3)*d
    cross=[(-7-d,5.5),(7+d,5.5),(7+d,6),(top,12+d),(-top,12+d),(-7-d,6)]
    face=b.Face(b.Wire.make_polygon([(x,-15,z) for x,z in cross],close=True))
    c=c.cut(b.Solid.extrude(face,(0,30,0)))
    c=c.fuse(box(p.probe_x-9,10,-10,2,20.5,26.5),box(p.probe_x-9,p.probe_x+9,-10,2,p.probe_z+3,26.5))
    u=p.probe_axis;start=(p.probe_x-6*u[0],-6*u[1],p.probe_z-6*u[2])
    c=c.fuse(cylinder(9,12,start,u))
    _,cy,cz=p.pinch_center
    c=c.fuse(box(p.probe_x-10,p.probe_x+10,cy-5,cy+5,cz-3,cz+3))
    web=b.Face(b.Wire.make_polygon([(p.probe_x+9,-10,p.probe_z+6),(p.probe_x+9,-10,20.5),(-15,-10,20.5)],close=True))
    c=c.fuse(b.Solid.extrude(web,(0,6,0)))
    c=c.cut(cylinder((p.probe_d+p.probe_clearance)/2,24,(p.probe_x-12*u[0],-12*u[1],p.probe_z-12*u[2]),u))
    # The probe lies in XY, with a radial collet slit toward the +Z lug.
    slit=box(-.45,.45,-9,9,p.probe_z,p.probe_z+10)
    c=c.cut(b.Pos(p.probe_x,0,0)*b.Rotation(0,0,p.approach_angle_degrees-90)*slit)
    c=c.cut(cylinder(p.m5_clearance/2,24,(p.probe_x-12,cy,cz),(1,0,0)))
    c=c.cut(cylinder(4.35,5.1,(p.probe_x+9.95,cy,cz),(1,0,0)))
    c=c.cut(b.Pos(p.probe_x-10.01,cy,cz)*b.Rotation(0,90,0)*hex_prism(8.3,0,4.1))
    c=c.cut(cylinder(p.m5_clearance/2,17,(0,0,13))).cut(hex_prism(8.3,20,4.2)).cut(box(0,16,-4.85,4.85,20,24.2))
    for y in (-8,8): c=c.cut(cylinder(2.1,7,(8.5,y,9),(1,0,0)))
    return c

def bearing(z=0,x=0,y=0,p=P):
    return cylinder(p.bearing_od/2,p.bearing_width,(x,y,z)).cut(cylinder(p.bearing_id/2,p.bearing_width+0.2,(x,y,z-0.1)))
def spacer(z,h,x=0,y=0): return cylinder(3.5,h,(x,y,z)).cut(cylinder(2.6,h+0.2,(x,y,z-0.1)))
def bolt(z,h,x=0,y=0,head=True):
    s=cylinder(2.5,h,(x,y,z)); return s.fuse(cylinder(4.25,3.5,(x,y,z+h))) if head else s
def nut(z,x=0,y=0): return hex_prism(8,z,4,x,y).cut(cylinder(2.5,5,(x,y,z-.5)))
def kinematics(phi,p=P):
    a=math.radians(phi); cx=p.crank_r*math.cos(a); cy=p.crank_r*math.sin(a)
    sy=cy-math.sqrt(p.rod_length**2-cx**2)
    return cx,cy,sy,-math.degrees(math.asin(cx/p.rod_length))

COLORS={'frame_front_clamp':'#547c8c','rear_clamp':'#729aa8','front_axle_bridge':'#729aa8','sector_crank':'#e7a82f','motor_pinion':'#d76f38','connecting_rod':'#32abad','probe_carriage':'#4976c1','NEMA17_body':'#303b46','NEMA17_face':'#c2cbd2','motor_shaft':'#bac7cf','microscope_reference':'#aebdc7','probe_reference':'#de4660','specimen_plate_reference':'#b6c7ba','optical_view_reference':'#8fcca2'}
PRINTABLE=['frame_front_clamp','rear_clamp','front_axle_bridge','sector_crank','motor_pinion','connecting_rod','probe_carriage']

def make_parts(phi=0,p=P,include_reference=True):
    if abs(phi)>p.limit+1e-7: raise ValueError(f'Angle must be within +/-{p.limit:.5f} degrees')
    cx,cy,sy,rodang=kinematics(phi,p)
    rodloc=b.Location((cx,cy,0),(0,0,rodang))
    parts={'frame_front_clamp':front_frame(p),'rear_clamp':clamp_half(False,p),'front_axle_bridge':front_axle_bridge(p),'sector_crank':b.Rotation(0,0,phi)*sector_wheel(p),'motor_pinion':b.Pos(-p.motor_offset,0,0)*b.Rotation(0,0,phi*p.ring_teeth/p.pinion_teeth)*involute_pinion(p),'connecting_rod':rodloc*connecting_rod(p),'probe_carriage':b.Pos(0,sy,0)*probe_carriage(p),'625ZZ_wheel_rear':bearing(6,p=p),'625ZZ_wheel_front':bearing(13,p=p),'625ZZ_crank':bearing(30,cx,cy,p),'625ZZ_slider':bearing(30,0,sy,p),'wheel_inner_spacer':spacer(11,2),'wheel_rear_spacer':spacer(4,2),'wheel_front_spacer':spacer(18,2),'crank_rear_spacer':spacer(14,16,cx,cy),'crank_front_spacer':spacer(35,2.2,cx,cy),'slider_rear_spacer':spacer(26.5,3.5,0,sy),'slider_front_spacer':spacer(35,2.2,0,sy),'M5_wheel_axle':bolt(-8,33),'M5_crank_bolt':cylinder(2.5,34.2,(cx,cy,8)).fuse(cylinder(4.25,3.5,(cx,cy,4.5))),'M5_crank_nut':nut(37.2,cx,cy),'M5_slider_pivot_bolt':bolt(18,19.2,0,sy),'M5_slider_captive_nut':nut(20,0,sy),'M5_axle_captive_nut':nut(-4)}
    x=-p.motor_offset; w=p.motor_size/2
    parts['NEMA17_body']=box(x-w,x+w,-w,w,-4-p.motor_length,-7)
    parts['NEMA17_face']=box(x-w,x+w,-w,w,-7,-4).fuse(cylinder(11,2,(x,0,-4)))
    shaft=cylinder(p.motor_shaft_d/2,24,(x,0,-2)).cut(box(x-5,x-2,-5,5,3,23))
    parts['motor_shaft']=b.Pos(x,0,0)*b.Rotation(0,0,phi*p.ring_teeth/p.pinion_teeth)*b.Pos(-x,0,0)*shaft
    for dx in (-p.motor_hole_spacing/2,p.motor_hole_spacing/2):
        for dy in (-p.motor_hole_spacing/2,p.motor_hole_spacing/2):
            xx=x+dx
            # Simplified motor reference has clear mounting bores; thread forms
            # are omitted so reference solids do not falsely collide with screws.
            bore=cylinder(1.55,10,(xx,dy,-12))
            parts['NEMA17_body']=parts['NEMA17_body'].cut(bore)
            parts['NEMA17_face']=parts['NEMA17_face'].cut(bore)
            parts[f'M3_motor_{dx}_{dy}']=cylinder(1.5,9,(xx,dy,-8)).fuse(cylinder(2.8,2.5,(xx,dy,1)))
    delta=math.degrees(2*math.asin(6/(2*p.stop_radius)))
    for sign in (-1,1):
        sx,ssy=polar(p.stop_radius,math.radians(sign*(p.limit+delta)))
        parts[f'M5_stop_{sign}']=cylinder(2.5,11.9,(sx,ssy,-4)).fuse(cylinder(4.25,3.5,(sx,ssy,-7.5)))
        parts[f'M5_stop_nut_{sign}']=nut(0,sx,ssy)
    for dx in (-28,28):
        parts[f'M5_clamp_{dx}']=to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*bolt(-13,25,dx,p.clamp_y),p)
        parts[f'M5_clamp_nut_{dx}']=to_local(b.Rotation(0,p.clamp_rotation_degrees,0)*nut(-12,dx,p.clamp_y),p)
    for i,(xx,yy) in enumerate(BRIDGE_POINTS):
        parts[f'M5_bridge_bolt_{i}']=bolt(-8,33,xx,yy)
        parts[f'M5_bridge_nut_{i}']=nut(-4,xx,yy)
    _,pcy,pcz=p.pinch_center
    parts['M5_probe_clamp_bolt']=cylinder(2.5,25,(p.probe_x-15,sy+pcy,pcz),(1,0,0)).fuse(cylinder(4.25,3.5,(p.probe_x+10,sy+pcy,pcz),(1,0,0)))
    parts['M5_probe_clamp_nut']=b.Pos(p.probe_x-10,sy+pcy,pcz)*b.Rotation(0,90,0)*nut(0)
    if include_reference:
        parts['microscope_reference']=to_local(cylinder(p.microscope_d/2,140,(0,0,0),(0,1,0)),p)
        u=p.probe_axis
        tip=(p.probe_x-p.probe_tip_extension*u[0],sy-p.probe_tip_extension*u[1],p.probe_z-p.probe_tip_extension*u[2])
        at=lambda t:(tip[0]+t*u[0],tip[1]+t*u[1],tip[2]+t*u[2])
        stem=cylinder(p.probe_stem_d/2,p.probe_stem_length-4,at(4),u)
        point=b.Solid.make_cone(0,p.probe_stem_d/2,4,b.Plane(origin=tip,z_dir=u))
        taper=b.Solid.make_cone(p.probe_stem_d/2,p.probe_d/2,p.probe_transition_length,b.Plane(origin=at(p.probe_stem_length),z_dir=u))
        shankstart=p.probe_stem_length+p.probe_transition_length
        shank=cylinder(p.probe_d/2,p.probe_total_length-shankstart,at(shankstart),u)
        parts['probe_reference']=point.fuse(stem,taper,shank)
        parts['specimen_plate_reference']=to_local(box(-50,50,-p.working_distance-3,-p.working_distance,-50,50),p)
    for name,shape in parts.items(): shape.label=name; shape.color=b.Color(COLORS.get(name,'#bdc7d0'))
    return parts

def controller_envelope(p=P):
    """Nominal 42 x 42 x 20 mm rear-controller reservation, not actual electronics CAD."""
    x=-p.motor_offset;w=p.motor_size/2;back=-4-p.motor_length
    return box(x-w,x+w,-w,w,back-p.controller_depth,back)

def controller_keepout(p=P,margin=None):
    """2 mm external allowance around the reservation, excluding the motor-side plane."""
    c=p.controller_clearance if margin is None else float(margin)
    if c<0: raise ValueError("Controller clearance margin must be nonnegative")
    x=-p.motor_offset;w=p.motor_size/2+c;back=-4-p.motor_length
    return box(x-w,x+w,-w,w,back-p.controller_depth-c,back)

def optical_keepout(p=P):
    """Central Ø44 projected optical column below the barrel; audit helper only."""
    return to_local(cylinder(p.microscope_d/2,p.working_distance,(0,-p.working_distance,0),(0,1,0)),p)

def conservative_probe(phi=0,p=P):
    """Worst case: pointed Ø6 probe throughout, used only for clearance audits."""
    sy=kinematics(phi,p)[2];u=p.probe_axis
    tip=(p.probe_x-p.probe_tip_extension*u[0],sy-p.probe_tip_extension*u[1],p.probe_z-p.probe_tip_extension*u[2])
    at=(tip[0]+4*u[0],tip[1]+4*u[1],tip[2]+4*u[2])
    return b.Solid.make_cone(0,p.probe_d/2,4,b.Plane(origin=tip,z_dir=u)).fuse(cylinder(p.probe_d/2,p.probe_total_length-4,at,u))

def motion(name):
    if name=='sector_crank': return 'wheel'
    if name in ['motor_pinion','motor_shaft']: return 'pinion'
    if name=='connecting_rod': return 'rod'
    if name in ['probe_carriage','probe_reference']: return 'slider'
    if name in ['625ZZ_crank','crank_rear_spacer','crank_front_spacer','M5_crank_bolt','M5_crank_nut']: return 'crank_pivot'
    if name in ['625ZZ_slider','slider_rear_spacer','slider_front_spacer','M5_slider_pivot_bolt','M5_slider_captive_nut','M5_probe_clamp_bolt','M5_probe_clamp_nut']: return 'slider_pivot'
    return 'fixed'

def export(out:Path,phi=None,p=P):
    out.mkdir(parents=True,exist_ok=True)
    if phi is None: phi=-p.limit  # Default assembly is the specimen contact pose.
    parts=make_parts(phi,p); zero=parts if phi==0 else make_parts(0,p)
    invalid=[n for n,s in list(parts.items())+list(zero.items()) if not s.is_valid or len(s.solids())!=1]
    if invalid: raise ValueError(f'Refusing to export invalid or disconnected parts: {invalid}')
    world=[to_world(s,p) for s in parts.values()]
    assembly=b.Compound(children=world,label='40 mm vertical microscope probe mechanism')
    b.export_step(assembly,out/'probe_stage_v4_assembly.step')
    # Separate reference boxes: reserved space, not a manufactured controller model.
    b.export_step(to_world(controller_envelope(p),p),out/'motor_controller_reserved_envelope.step')
    b.export_step(to_world(controller_keepout(p),p),out/'motor_controller_clearance_keepout.step')
    b.export_gltf(assembly,out/'probe_stage_v4_assembly.glb',binary=True,linear_deflection=.10,angular_deflection=.25)
    pd=out/'parts';pd.mkdir(exist_ok=True)
    for name,shape in parts.items():
        # Every displayed model has its own STEP, in its assembly position.
        b.export_step(to_world(shape,p),pd/f'{name}.step')
        if name in PRINTABLE:
            b.export_stl(to_world(shape,p),pd/f'{name}.stl',tolerance=.08,angular_tolerance=.2)
    lo=kinematics(-p.limit,p)[2];hi=kinematics(p.limit,p)[2]
    conservative_min_x=(p.working_distance-p.stroke)/math.tan(math.radians(p.approach_angle_degrees))-(p.probe_d/2)/math.sin(math.radians(p.approach_angle_degrees))
    report={'parameters':asdict(p),'derived':{'vertical_travel_mm':hi-lo,'horizontal_travel_mm':0,'probe_axis_angle_from_plate_degrees':p.approach_angle_degrees,'wheel_limit_degrees':p.limit,'wheel_sweep_degrees':2*p.limit,'motor_to_wheel_ratio':p.ring_teeth/p.pinion_teeth,'motor_travel_degrees':2*p.limit*p.ring_teeth/p.pinion_teeth,'pinion_to_window_inner_clearance_mm':p.motor_offset-(p.pinion_pitch_r+p.module)-p.window_inner_r,'pinion_to_slot_end_clearance_mm':p.motor_offset*math.cos(math.radians(p.limit))-(p.pinion_pitch_r+p.module),'world_origin_mm':p.world_origin,'drive_plane_yaw_degrees':p.drive_yaw_degrees,'wheel_outer_diameter_mm':2*p.wheel_r,'carriage_y_low':lo,'carriage_y_high':hi,'clamp_band_world_y_mm':[0,p.clamp_width],'clamp_half_closure_clearance_mm':parts['frame_front_clamp'].distance_to(parts['rear_clamp']),'conservative_6mm_probe_min_x_at_barrel_end_full_retraction_mm':conservative_min_x,'conservative_6mm_probe_to_clamp_envelope_clearance_mm':conservative_min_x-p.clamp_outer_r,'optical_projection_radius_mm':p.microscope_d/2,'controller_nominal_dimensions_mm':[p.motor_size,p.motor_size,p.controller_depth],'controller_clearance_mm':p.controller_clearance,'controller_world_bounds_mm':{'min':list(to_world(controller_envelope(p),p).bounding_box().min),'max':list(to_world(controller_envelope(p),p).bounding_box().max)},'controller_keepout_world_bounds_mm':{'min':list(to_world(controller_keepout(p),p).bounding_box().min),'max':list(to_world(controller_keepout(p),p).bounding_box().max)},'controller_note':'42 x 42 x 20 mm reserved rear volume plus 2 mm clearance; actual electronics geometry and mass are not modeled. Rear faces tangentially away from the microscope.','probe_reference_note':'Customizable reference: 1 mm stem, taper to 6 mm shank outside the central optical projection; collet center 90 mm from tip. Conservative full-length 6 mm clearance envelope available via conservative_probe().'},'parts':{n:{'valid':s.is_valid,'solids':len(s.solids()),'volume_mm3':s.volume} for n,s in parts.items()}}
    report['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out/'dimensions_and_checks.json').write_text(json.dumps(report,indent=2))
    meshes=[]
    for name,shape in zero.items():
        vs,ts=shape.tessellate(.16,.3)
        meshes.append({'name':name,'color':COLORS.get(name,'#bdc7d0'),'vertices':[[round(v.X,5),round(v.Y,5),round(v.Z,5)] for v in vs],'triangles':[list(t) for t in ts],'motion':motion(name),'reference':name.endswith('_reference'),'opacity':.3 if name=='microscope_reference' else (.65 if name=='specimen_plate_reference' else 1),'download':f'parts/{name}.step','xt':None})
    kmeta={'crank_radius':p.crank_r,'rod_length':p.rod_length,'phi_min':math.radians(-p.limit),'phi_max':math.radians(p.limit),'angle_units':'radians','pinion_ratio':p.ring_teeth/p.pinion_teeth,'pinion_center':[-p.motor_offset,0,0],'world_transform':{'rotation_deg':p.tilt,'rotation_y_deg':p.drive_yaw_degrees,'translation':p.world_origin},'reference_phi':0,'slider_y_low':lo,'slider_y_high':hi,'hardware_notes':['Use a smooth precision 5 mm running section through each 625ZZ inner race, with M5 threads outside the races or a custom axle.','Modeled M5 heads are low-profile 8.5 mm diameter x 3.5 mm high. Verify supplied screw head envelopes.','Nominal 6 mm shoulder bolts do not fit 5 mm-bore 625ZZ bearings.','M5 clearance holes are nominally 5.3 mm. Calibrate printed fits and bearing seats before assembly.'],'manufacturing_notes':['Individual STEP and STL files share the contact-pose assembly placement. Arrange STL orientations for manufacture.']}
    (out/'viewer_meshes.json').write_text(json.dumps({'meta':{'units':'mm','localToWorld':{'rotationZDegrees':p.tilt,'rotationYDegrees':p.drive_yaw_degrees,'translation':p.world_origin},'crankRadius':p.crank_r,'rodLength':p.rod_length,'stroke':p.stroke,'travelType':'vertical','limitDegrees':p.limit,'ratio':p.ring_teeth/p.pinion_teeth,'pinionCenter':[-p.motor_offset,0,0],'sliderY0':kinematics(0,p)[2],'rodAngle0':kinematics(0,p)[3],'workingDistance':p.working_distance,'specimen_plate_y':-p.working_distance,'approachAngle':p.approach_angle_degrees,'probeStemDiameter':p.probe_stem_d,'probeShankDiameter':p.probe_d,'probeReferenceOnly':True,'optical_keepout':{'radius_mm':p.microscope_d/2,'working_distance_mm':p.working_distance,'margin_radius_mm':p.microscope_d/2+2,'barrel_end_y':0,'specimen_y':-p.working_distance,'center_x':0,'center_z':0,'projection_assumption':True},'printable':PRINTABLE,'controllerReservation':{'reference_only':True,'nominal_dimensions_mm':[p.motor_size,p.motor_size,p.controller_depth],'clearance_mm':p.controller_clearance,'rear_normal_world':[0,0,-1],'local_box_min':[-p.motor_offset-p.motor_size/2,-p.motor_size/2,-4-p.motor_length-p.controller_depth],'local_box_max':[-p.motor_offset+p.motor_size/2,p.motor_size/2,-4-p.motor_length],'keepout_local_box_min':[-p.motor_offset-p.motor_size/2-p.controller_clearance,-p.motor_size/2-p.controller_clearance,-4-p.motor_length-p.controller_depth-p.controller_clearance],'keepout_local_box_max':[-p.motor_offset+p.motor_size/2+p.controller_clearance,p.motor_size/2+p.controller_clearance,-4-p.motor_length],'note':'Space reserved for a back-mounted motor controller; this is not actual controller electronics CAD.'},'kinematics':kmeta},'parts':meshes},separators=(',',':')))
    source=Path(__file__).resolve()
    if source!=(out/'probe_stage_v4.py').resolve(): shutil.copy2(source,out/'probe_stage_v4.py')
    (out/'requirements.txt').write_text('build123d==0.10.0\n')
    print(json.dumps({'out':str(out),'parts':len(parts),'travel':hi-lo,'angle_limit':p.limit,'invalid':[n for n,s in parts.items() if not s.is_valid],'multiple_solids':{n:len(s.solids()) for n,s in parts.items() if len(s.solids())!=1}},indent=2),flush=True)
    return zero

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=Path('work/v4_frame_design/output'))
    ap.add_argument('--angle',type=float,default=None,help='Wheel angle in degrees; omitted defaults to the lower contact pose.')
    ap.add_argument('--working-distance',type=float,default=100)
    args=ap.parse_args();P.working_distance=args.working_distance;export(args.out,args.angle,P)
