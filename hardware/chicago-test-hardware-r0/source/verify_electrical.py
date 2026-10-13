"""Cross-check independent schematic netlist, PCB pins and exported drill files."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
board=k.LoadBoard(str(ROOT/'pcb'/'sensor-interface.kicad_pcb'))
xml=ET.parse(ROOT/'validation'/'schematic-netlist.xml')
expected={
 '3V3_IN': {('J1','1'),('JP1','1')},
 '3V3_SENSOR': {('J2','1'),('JP1','2'),('TP1','1')},
 'GND': {('J1','2'),('J2','2'),('TP2','1')},
 'SDA': {('J1','3'),('J2','3'),('TP3','1')},
 'SCL': {('J1','4'),('J2','4'),('TP4','1')},
}
schematic={net.attrib['name'].lstrip('/'): {(n.attrib['ref'],n.attrib['pin']) for n in net.findall('node')} for net in xml.findall('./nets/net')}
actual={name:set() for name in expected}
for f in board.GetFootprints():
 for p in f.Pads():
  if p.GetNetname(): actual[p.GetNetname()].add((f.GetReference(),p.GetNumber()))
assert schematic==expected, ('Schematic mismatch',schematic)
assert actual==expected, ('PCB mismatch',actual)
# Check coordinates against the part data and mechanical mating pattern.
pads={(f.GetReference(),p.GetNumber()):(round(k.ToMM(p.GetPosition().x),4),round(k.ToMM(p.GetPosition().y),4)) for f in board.GetFootprints() for p in f.Pads()}
for ref,x in [('J1',8),('J2',42)]:
 for i,y in enumerate([12,14.54,17.08,19.62],1): assert pads[ref,str(i)]==(x,y)
assert pads['JP1','1']==(23.73,8) and pads['JP1','2']==(26.27,8)
assert [pads['H'+str(i),''] for i in range(1,5)]==[(4,4),(46,4),(4,31),(46,31)]
for kind,count,diameter in [('PTH',10,'1.020'),('NPTH',4,'3.200')]:
 text=(ROOT/'manufacturing'/'gerbers'/f'sensor-interface-{kind}.drl').read_text()
 assert len(re.findall(r'^X[-\d.]+Y[-\d.]+$',text,re.M))==count
 assert 'T1C'+diameter in text
report=(ROOT/'validation'/'pcb-drc.txt').read_text()
assert 'Found 0 DRC violations' in report and 'Found 0 unconnected pads' in report
result={'schematic_matches_intended_nets':True,'pcb_matches_schematic':True,'net_count':5,
        'plated_holes':10,'nonplated_holes':4,'header_pitch_mm':2.54,'pcb_mount_pattern_mm':[42,27],
        'drc_violations':0,'unconnected_pads':0,'physical_validation':'NOT RUN',
        'schematic_erc':'KiCad 7 CLI has no ERC command; passive pin connectivity verified by netlist comparison, not a claimed ERC run.'}
(ROOT/'validation'/'electrical.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
