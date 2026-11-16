import sys
R='/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1'
sys.path.insert(0,R+'/cage'); sys.path.insert(0,R+'/layout')
import cage as C, stack as st
S=st.S
for b in st.ORDER: print(b,'card_z',round(st.card_z(b),3),'slot',round(st.card_z(b)-st.BT-C.SLOT_CLEAR/2,3),round(st.card_z(b)+C.SLOT_CLEAR/2,3))
print('BT',st.BT,'CD',st.CD,'BW',st.BW,'CAGE_LEFT',st.CAGE_LEFT,'RX',C.RX,'CARD_FRONT',C.CARD_FRONT,'Z_LO',C.Z_LO,'Z_HI',C.Z_HI)
print('BP_BACK',st.BP_BACK,'BP_FRONT',st.BP_FRONT,'OUTLINE',st.BP_OUTLINE,'GROOVE',C.GROOVE,'RSLOT',C.RSLOT,'RAIL_Z0',C.RAIL_Z0,'RAIL_Y1',C.RAIL_Y1)
print('post_y1',C.CARD_FRONT-(S.val('sb_snap_y')-1.5),'BOB_Y',st.BOB_Y,'TONGUE_Y1',st.TONGUE_Y1, 'Y_BP',st.Y_BP)
print('supports',[st.bp_xy(h) for h in st.BP_SUPPORTS])
for p in C.parts():
  print('==',p.name)
  for b in p.boxes: print('  box',b.what,[round(v,2) for v in (b.x0,b.x1,b.y0,b.y1,b.z0,b.z1)])
  for b in p.cuts: print('  cut',b.what,[round(v,2) for v in (b.x0,b.x1,b.y0,b.y1,b.z0,b.z1)])
print('W H D',C.W,C.H,C.D,'SEAM',C.SEAM)
print('EVM',C.EVM_X0,C.EVM_Y0,C.EVM_Z0,C.EVM_TOP,'PACK_TRAY_Z',C.PACK_TRAY_Z)
print('bar',S.val('bar'))
