"""Generate a minimal passive 3.3 V sensor bench interface using KiCad 7 pcbnew.

No RF, power conversion, battery connection or outdoor cable interface is present.
"""
from pathlib import Path
import json
import uuid
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'pcb'
LIB=OUT/'Bench.pretty'
LIB.mkdir(exist_ok=True)
b=k.BOARD()
b.SetCopperLayerCount(2)
b.GetDesignSettings().SetBoardThickness(k.FromMM(1.6))
net_names=['3V3_IN','3V3_SENSOR','GND','SDA','SCL']
nets={}
for name in net_names:
    net=k.NETINFO_ITEM(b,name)
    b.Add(net)
    nets[name]=net


def layers(*ids):
    result=k.LSET()
    for i in ids: result.AddLayer(i)
    return result

def identity(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,"weather-station-r0/"+name))

def xy(x,y):
    return k.VECTOR2I(k.FromMM(x),k.FromMM(y))


def line(owner,a,z,layer,width=0.15):
    item=k.FP_SHAPE(owner) if isinstance(owner,k.FOOTPRINT) else k.PCB_SHAPE(owner)
    item.SetShape(k.SHAPE_T_SEGMENT)
    item.SetStart(xy(*a)); item.SetEnd(xy(*z))
    if isinstance(owner,k.FOOTPRINT):
        item.SetStart0(xy(*a)); item.SetEnd0(xy(*z))
    item.SetLayer(layer); item.SetWidth(k.FromMM(width)); owner.Add(item)


def rect(owner,x,y,w,h,layer,width=0.15):
    for a,z in [((x,y),(x+w,y)),((x+w,y),(x+w,y+h)),((x+w,y+h),(x,y+h)),((x,y+h),(x,y))]:
        line(owner,a,z,layer,width)


def text(value,x,y,size=1,layer=k.F_SilkS):
    item=k.PCB_TEXT(b); item.SetText(value); item.SetPosition(xy(x,y))
    item.SetTextSize(xy(size,size)); item.SetTextThickness(k.FromMM(0.15))
    item.SetLayer(layer); b.Add(item)


def header(ref,x,y,names,horizontal=False):
    """Samtec TSW: 2.54 pitch, 1.02 mm finished holes, 2.0 mm pads."""
    f=k.FOOTPRINT(b); f.SetReference(ref); f.SetValue('TSW-10%d-07-G-S'%len(names))
    f.SetAttributes(k.FP_THROUGH_HOLE)
    name='Header_1x%02d_%s'%(len(names),'HorizontalRow' if horizontal else 'VerticalRow')
    f.SetFPID(k.LIB_ID('Bench',name))
    for i,net_name in enumerate(names):
        p=k.PAD(f); p.SetNumber(str(i+1)); p.SetAttribute(k.PAD_ATTRIB_PTH)
        p.SetShape(k.PAD_SHAPE_RECT if i==0 else k.PAD_SHAPE_CIRCLE)
        p.SetSize(xy(2,2)); p.SetDrillSize(xy(1.02,1.02)); p.SetLayerSet(layers(k.F_Cu,k.B_Cu,k.F_Mask,k.B_Mask))
        p.SetPosition(xy(i*2.54 if horizontal else 0,0 if horizontal else i*2.54))
        p.SetPos0(p.GetPosition()); p.SetNet(nets[net_name]); f.Add(p)
    w=len(names)*2.54 if horizontal else 2.54
    h=2.54 if horizontal else len(names)*2.54
    rect(f,-1.27,-1.27,w,h,k.F_Fab,0.1)
    rect(f,-1.65,-1.65,w+0.76,h+0.76,k.F_CrtYd,0.05)
    f.Reference().SetPosition(xy(w/2-1.27,-2.5)); f.Reference().SetTextSize(xy(1,1)); f.Reference().SetTextThickness(k.FromMM(0.15))
    f.Reference().SetPos0(f.Reference().GetPosition())
    f.Value().SetVisible(False)
    k.FootprintSave(str(LIB),f)
    f.SetPosition(xy(x,y)); b.Add(f)
    return f

header('J1',8,12,['3V3_IN','GND','SDA','SCL'])
header('J2',42,12,['3V3_SENSOR','GND','SDA','SCL'])
header('JP1',23.73,8,['3V3_IN','3V3_SENSOR'],True)


def track(name,points):
    for a,z in zip(points,points[1:]):
        t=k.PCB_TRACK(b); t.SetStart(xy(*a));t.SetEnd(xy(*z))
        t.SetLayer(k.F_Cu);t.SetWidth(k.FromMM(0.5));t.SetNet(nets[name]);b.Add(t)

track('3V3_IN',[(8,12),(12,8),(23.73,8)])
track('3V3_SENSOR',[(26.27,8),(38,8),(42,12)])
for net,y in [('GND',14.54),('SDA',17.08),('SCL',19.62)]:
    track(net,[(8,y),(42,y)])

for ref,net,x,y in [('TP1','3V3_SENSOR',35,8),('TP2','GND',25,14.54),('TP3','SDA',25,17.08),('TP4','SCL',25,19.62)]:
    f=k.FOOTPRINT(b); f.SetReference(ref); f.SetValue(net)
    f.SetFPID(k.LIB_ID('Bench','TestPad_1.5mm'))
    f.SetAttributes(k.FP_SMD | k.FP_EXCLUDE_FROM_BOM | k.FP_EXCLUDE_FROM_POS_FILES)
    p=k.PAD(f);p.SetNumber('1');p.SetAttribute(k.PAD_ATTRIB_SMD);p.SetShape(k.PAD_SHAPE_CIRCLE)
    p.SetSize(xy(1.5,1.5));p.SetLayerSet(layers(k.F_Cu,k.F_Mask));p.SetNet(nets[net]);f.Add(p)
    rect(f,-0.85,-0.85,1.7,1.7,k.F_CrtYd,0.05)
    f.Reference().SetVisible(False);f.Value().SetVisible(False)
    k.FootprintSave(str(LIB),f);f.SetPosition(xy(x,y));b.Add(f)
    # Place test labels clear of exposed copper.
    text(ref,x+3,y,0.8)

for i,(x,y) in enumerate([(4,4),(46,4),(4,31),(46,31)],1):
    f=k.FOOTPRINT(b);f.SetReference('H'+str(i));f.SetValue('M3_NPTH')
    f.SetFPID(k.LIB_ID('Bench','MountingHole_3.2mm'))
    f.SetAttributes(k.FP_EXCLUDE_FROM_BOM|k.FP_EXCLUDE_FROM_POS_FILES)
    p=k.PAD(f);p.SetNumber('');p.SetAttribute(k.PAD_ATTRIB_NPTH);p.SetShape(k.PAD_SHAPE_CIRCLE)
    p.SetSize(xy(3.2,3.2));p.SetDrillSize(xy(3.2,3.2));p.SetLayerSet(layers(k.F_Cu,k.B_Cu,k.F_Mask,k.B_Mask));f.Add(p)
    rect(f,-3,-3,6,6,k.F_CrtYd,0.05)
    f.Reference().SetVisible(False);f.Value().SetVisible(False)
    k.FootprintSave(str(LIB),f);f.SetPosition(xy(x,y));b.Add(f)

rect(b,0,0,50,35,k.Edge_Cuts,0.05)
text('WS CHICAGO / SENSOR TEST R0',25,2.5,0.9)
text('HOST',8,6,0.9);text('SENSOR',42,6,0.9)
for y,s in [(12,'3V3'),(14.54,'GND'),(17.08,'SDA'),(19.62,'SCL')]:
    text(s,13,y,0.9);text(s,37,y,0.9)
text('JP1: FIT SHUNT TO RUN',25,24,1)
text('3.3V ONLY / BENCH USE',25,27,1)
text('1 = SQUARE PAD',25,31,0.9)
text('50 x 35 mm / R0',25,17,1.2,k.B_SilkS)
# Mirror back-side text for physical readability.
for d in b.GetDrawings():
    if isinstance(d,k.PCB_TEXT) and d.GetLayer()==k.B_SilkS: d.SetMirrored(True)

for f in b.GetFootprints():
    f.SetPath(k.KIID_PATH("/"+identity("root")+"/"+identity(f.GetReference())))
b.BuildConnectivity()
k.SaveBoard(str(OUT/'sensor-interface.kicad_pcb'),b)
(OUT/'fp-lib-table').write_text('(fp_lib_table (lib (name "Bench")(type "KiCad")(uri "${KIPRJMOD}/Bench.pretty")(options "")(descr "Self-contained bench fixture footprints")))\n')
project={'board':{'design_settings':{'rules':{'min_clearance':0.25,'min_track_width':0.25,'min_copper_edge_clearance':0.5,'min_through_hole_diameter':0.3,'min_hole_to_hole':0.25,'min_via_annular_width':0.15}}},'net_settings':{'classes':[{'name':'Default','clearance':0.25,'track_width':0.5,'via_diameter':0.8,'via_drill':0.4}],'meta':{'version':3}},'meta':{'version':1}}
(OUT/'sensor-interface.kicad_pro').write_text(json.dumps(project,indent=2))
# Reload with project settings for the same checks a KiCad user sees.
b=k.LoadBoard(str(OUT/'sensor-interface.kicad_pcb'))
settings=b.GetDesignSettings()
settings.m_MinClearance=k.FromMM(0.25)
settings.m_CopperEdgeClearance=k.FromMM(0.5)
settings.m_TrackMinWidth=k.FromMM(0.25)
assert k.WriteDRCReport(b,str(ROOT/'validation'/'pcb-drc.txt'),k.EDA_UNITS_MILLIMETRES,True)
print('PCB generated; see validation/pcb-drc.txt')
