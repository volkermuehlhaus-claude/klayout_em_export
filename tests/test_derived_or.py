# Batch test (KLayout -z -nc -rx -r): a stackup whose Metal1 is the OR of two layer numbers, Metal1 = 8/0 OR 9/0.
# Each operand alone may hold islands that float and repeat but are joined to a via through the other operand: those
# are no dummy fill. And a cheesed plane drawn as 8/0 stripes crossed by 9/0 stripes has its holes only in the
# combined metal: Fill Density Holes and Merge Metal finds them there. No PDK needed.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
import pya
from klayout_em_export.density import fill_and_merge, merged_layers
from klayout_em_export.dummyfill import fill_layers, find_fill, remove_dummy_fill
from klayout_em_export.layers import region
from klayout_em_export.stackup import Stackup, layer_key

OUT = os.environ.get("OUT", ".")
os.makedirs(OUT, exist_ok=True)
failed = []


def check(ok, text):
    print(("ok    " if ok else "FAIL  ") + text)
    if not ok:
        failed.append(text)


XML = '''<?xml version="1.0" encoding="UTF-8"?>
<Stackup schemaVersion="3.2">
  <Materials>
    <Material Name="Cu" Type="Conductor" Conductivity="5.8e7" />
    <Material Name="Ox" Type="Dielectric" Permittivity="4" />
  </Materials>
  <ELayers LengthUnit="um">
    <Dielectrics>
      <Dielectric Name="Ox" Material="Ox" Zmin="0" Zmax="10" />
    </Dielectrics>
    <Layers>
      <Layer Name="Metal2" Type="conductor" Material="Cu" Layer="10" Zmin="3" Zmax="4" />
      <Layer Name="Via1" Type="via" Material="Cu" Layer="19" Zmin="2" Zmax="3" />
      <Layer Name="Metal1" Type="conductor" Material="Cu" Layer="908" Zmin="1" Zmax="2" />
    </Layers>
    <DerivedLayers>
      <DerivedLayer Name="Metal1" Layer="908" Operation="OR">
        <Operand Layer="8" />
        <Operand Layer="9" />
      </DerivedLayer>
    </DerivedLayers>
  </ELayers>
</Stackup>'''
path = os.path.join(OUT, "derived_or_stackup.xml")
open(path, "w").write(XML)
st = Stackup(path)

check(st.metal_sources(908) == {8, 9}, f"both operands of the OR are metal: {st.metal_sources(908)}")
check({8, 9, 10} <= set(fill_layers(st)) and 19 not in fill_layers(st), f"fill searched on 8, 9, 10: {fill_layers(st)}")
check({8, 9, 10} <= set(merged_layers(st)), "8 and 9 filled and merged")


def um(x0, y0, x1, y1):
    return pya.DBox(x0, y0, x1, y1).to_itype(0.001)


ly = pya.Layout()
ly.dbu = 0.001
top = ly.create_cell("TOP")
m8, m9, v1 = ly.layer(8, 0), ly.layer(9, 0), ly.layer(19, 0)
for i in range(30):
    x = 10 * i
    # joined: a 2x2 island on 8/0 overlapping a 2x2 island on 9/0, the via on the 9/0 part only
    top.shapes(m8).insert(um(x, 0, x + 2, 2))
    top.shapes(m9).insert(um(x + 1, 0, x + 3, 2))
    top.shapes(v1).insert(um(x + 2.2, 0.5, x + 2.8, 1.5))
    # fill: floating tiles on 8/0 and on 9/0
    top.shapes(m8).insert(um(x, 10, x + 2, 12))
    top.shapes(m9).insert(um(x, 20, x + 2, 22))

check(region(ly, top, st, 908, um(-1, -1, 3, 3)).count() == 1, "an 8/0 island and its 9/0 island are one Metal1 polygon")
fill = find_fill(ly, top, st)
check(set(fill) == {(8, 0), (9, 0)}, f"fill on 8/0 and 9/0: {sorted(fill)}")
check(fill[(8, 0)].count() == 30 and fill[(8, 0)].bbox() == um(0, 10, 292, 12),
      f"8/0: only the 30 floating tiles, not the islands joined to a via through 9/0 ({fill[(8, 0)].count()})")
check(fill[(9, 0)].count() == 30 and fill[(9, 0)].bbox() == um(0, 20, 292, 22),
      f"9/0: only the 30 floating tiles ({fill[(9, 0)].count()})")
removed, _ = remove_dummy_fill(ly, top, st)
check(removed == {(8, 0): 30, (9, 0): 30}, f"removed: {removed}")
check(pya.Region(top.begin_shapes_rec(m8)).count() == 30 and pya.Region(top.begin_shapes_rec(m9)).count() == 30,
      "the joined islands stay")

# a cheesed plane: 6 horizontal 8/0 stripes crossed by 6 vertical 9/0 stripes, 25 openings of 4 x 4 that are holes
# of the combined metal only (no operand has a hole of its own)
ly2 = pya.Layout()
ly2.dbu = 0.001
top2 = ly2.create_cell("TOP")
for k in range(6):
    top2.shapes(ly2.layer(8, 0)).insert(um(0, 6 * k, 32, 6 * k + 2))
    top2.shapes(ly2.layer(9, 0)).insert(um(6 * k, 0, 6 * k + 2, 32))
before = region(ly2, top2, st, 908)
check(sum(p.holes() for p in before.each()) == 25, "the combined metal has 25 holes")
result, _ = fill_and_merge(ly2, top2, st)
check("Metal1 (8/0)" in result and result["Metal1 (8/0)"].filled == 25,
      f"filled on 8/0: {[(n, r.filled) for n, r in result.items()]}")
after = region(ly2, top2, st, 908)
check(after.count() == 1 and sum(p.holes() for p in after.each()) == 0, "Metal1 is one solid plate afterwards")
check(pya.Region(top2.begin_shapes_rec(ly2.layer(9, 0))).merged().count() == 6, "the 9/0 stripes are left as drawn")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
