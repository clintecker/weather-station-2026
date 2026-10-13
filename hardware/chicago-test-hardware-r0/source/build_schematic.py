"""Generate a self-contained native KiCad schematic for the passive test fixture."""
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'pcb'

def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'weather-station-r0/'+name))

def prop(name,value,x,y,hide=False):
    return f'(property "{name}" "{value}" (at {x} {y} 0) (effects (font (size 1.27 1.27)){" hide" if hide else ""}))'

def symbol_def(name,n):
    pins=''.join(f'''(pin passive line (at -5.08 {-i*2.54} 0) (length 2.54)
        (name "{i+1}" (effects (font (size 1 1)))) (number "{i+1}" (effects (font (size 1 1)))))''' for i in range(n))
    return f'''(symbol "Bench:{name}" (pin_names hide) (in_bom yes) (on_board yes)
      {prop('Reference','J',0,3.81)} {prop('Value',name,0,6.35)}
      (symbol "{name}_0_1" (rectangle (start -2.54 1.27) (end 2.54 {-max(0,n-1)*2.54-1.27}) (stroke (width 0.254) (type default)) (fill (type background))))
      (symbol "{name}_1_1" {pins}))'''

lib=''.join(symbol_def(name,n) for name,n in [('Conn4',4),('Conn2',2),('TestPad',1),('Mount',0)])
parts=[
 ('J1','Conn4','HOST_3V3','Header_1x04_VerticalRow',60,55,['3V3_IN','GND','SDA','SCL']),
 ('J2','Conn4','SENSOR_3V3','Header_1x04_VerticalRow',155,55,['3V3_SENSOR','GND','SDA','SCL']),
 ('JP1','Conn2','CURRENT_LINK','Header_1x02_HorizontalRow',110,87,['3V3_IN','3V3_SENSOR']),
 ('TP1','TestPad','3V3_SENSOR','TestPad_1.5mm',60,108,['3V3_SENSOR']),
 ('TP2','TestPad','GND','TestPad_1.5mm',60,124,['GND']),
 ('TP3','TestPad','SDA','TestPad_1.5mm',110,108,['SDA']),
 ('TP4','TestPad','SCL','TestPad_1.5mm',110,124,['SCL']),
 *[(f'H{i+1}','Mount','M3_NPTH','MountingHole_3.2mm',155+i*14,108,[]) for i in range(4)]
]
items=[]
for ref,name,value,foot,x,y,nets in parts:
    items.append(f'''(symbol (lib_id "Bench:{name}") (at {x} {y} 0) (unit 1)
      (in_bom {"no" if ref.startswith(('TP','H')) else "yes"}) (on_board yes) (dnp no) (uuid {uid(ref)})
      {prop('Reference',ref,x,y-5.08)} {prop('Value',value,x,y-2.54)}
      {prop('Footprint','Bench:'+foot,x,y,True)}
      (instances (project "sensor-interface" (path "/{uid('root')}" (reference "{ref}") (unit 1)))))''')
    for i,net in enumerate(nets):
        yy=y+i*2.54
        items.append(f'''(wire (pts (xy {x-25.4} {yy}) (xy {x-5.08} {yy})) (stroke (width 0) (type default)) (uuid {uid(ref+'wire'+str(i))}))
        (label "{net}" (at {x-25.4} {yy} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {uid(ref+'label'+str(i))}))''')
notes=[('WS Chicago R0 - passive 3.3 V sensor test interface',35,28),
       ('J1/J2: 1=3V3, 2=GND, 3=SDA, 4=SCL. Pin 1 is square on PCB.',35,145),
       ('JP1 fitted: normal operation. Replace shunt with series ammeter for sensor current.',35,152),
       ('No pullups fitted here: use SHT45 breakout pullups. Disable MCU internal pullups.',35,159),
       ('3.3 V only. No battery input. No RJ45. No outdoor exposure.',35,166),
       ('TP1-4 are bare copper probe pads; H1-4 are 3.2 mm non-plated holes.',35,173)]
for i,(note,x,y) in enumerate(notes):
    items.append(f'(text "{note}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (justify left)) (uuid {uid("note"+str(i))}))')
s=f'''(kicad_sch (version 20230121) (generator eeschema) (uuid {uid('root')}) (paper "A4")
(title_block (title "Chicago Stage 0 Sensor Bench Interface") (date "2026-10-08") (rev "R0"))
(lib_symbols {lib})
{''.join(items)}
(sheet_instances (path "/" (page "1"))))\n'''
(OUT/'sensor-interface.kicad_sch').write_text(s)
(OUT/'Bench.kicad_sym').write_text('(kicad_symbol_lib (version 20220914) (generator kicad_symbol_editor) '+lib.replace('Bench:','')+')\n')
(OUT/'sym-lib-table').write_text('(sym_lib_table (lib (name "Bench")(type "KiCad")(uri "${KIPRJMOD}/Bench.kicad_sym")(options "")(descr "Passive test fixture symbols")))\n')
print('Native schematic and symbols generated')
