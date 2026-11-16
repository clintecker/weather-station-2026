import sys
sys.dont_write_bytecode = True
sys.argv = ["x"]
import scenes2 as S
s = S.top_scene(["U2"], under=False, decals=False)
S.R("z_ina", s, (0, 0, 1), up=(0, 1, 0), fit=(300, 220), line=0.4, crop=((17.8, 9, 5), 11, 8))
print(S.PL["U2"]["pads"], S.PL["U2"]["step"])
