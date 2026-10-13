proc rm32 {a} { return [read_memory $a 32 1] }
init
reset halt
wp 0x48000000 4 w
set prev [rm32 0x48000000]
for {set i 0} {$i < 200} {incr i} {
  if {[catch {resume; wait_halt 1500} r]} { echo "LOST after $i hits: $r"; break }
  set m [rm32 0x48000000]
  set pc [lindex [get_reg pc] 1]
  if {$m != $prev} { echo [format "HIT %d PC=%s MODER 0x%08x -> 0x%08x  U2CR1=0x%08x U2BRR=0x%08x LP1CR1=0x%08x" $i $pc $prev $m [rm32 0x40004400] [rm32 0x4000440C] [rm32 0x40008000]]; set prev $m }
}
echo [format "final MODER=0x%08x U2CR1=0x%08x U2BRR=0x%08x LP1CR1=0x%08x LP1BRR=0x%08x" [rm32 0x48000000] [rm32 0x40004400] [rm32 0x4000440C] [rm32 0x40008000] [rm32 0x4000800C]]
shutdown
