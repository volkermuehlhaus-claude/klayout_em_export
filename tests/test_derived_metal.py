# Batch test (KLayout -z -nc -rx -r): a stackup whose Metal1 is a derived layer, Metal1 = 8/0 NOT 8/24 (slits cut
# out of the drawn metal), as in a designer's slit study. The checks trace Metal1 as gds2palace computes it: the
# ground marks accept a shape drawn on 8/0, the slits separate the pieces, the vias on Via1 reach it, and the EM Port
# tool finds its edges. A derived sheet (a resistor) is no wiring and stays out. No PDK needed.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
import pya
from klayout_em_export import gui
from klayout_em_export.connectivity import check_ground, wiring
from klayout_em_export.export import export_flat
from klayout_em_export.layers import polygon_at, region
from klayout_em_export.locate import drawn_metals, edge_at, metals_at
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
    <Material Name="Rs" Type="Resistor" Rs="100" />
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
      <Layer Name="RS" Type="sheet" Material="Rs" Layer="312" Zmin="0.5" Zmax="0.5" />
    </Layers>
    <DerivedLayers>
      <DerivedLayer Name="Metal1" Layer="908" Operation="NOT">
        <Operand Layer="8" Datatype="0" />
        <Operand Layer="8" Datatype="24" />
      </DerivedLayer>
      <DerivedLayer Name="RS" Layer="312" Operation="AND">
        <Operand Layer="5" />
        <Operand Layer="7" />
      </DerivedLayer>
    </DerivedLayers>
  </ELayers>
</Stackup>'''
path = os.path.join(OUT, "derived_metal_stackup.xml")
open(path, "w").write(XML)
st = Stackup(path)

metals, connections = wiring(st)
check(metals == {10: "Metal2", 908: "Metal1"}, f"traced: {metals} (the derived Metal1, not the derived sheet RS)")
check(connections == [(19, 908, 10)], f"Via1 connects Metal1 and Metal2: {connections}")
check(drawn_metals(st) == [("Metal2", 10), ("Metal1", 908)], "the EM Port tool searches Metal1 too")
check(st.sources(908) == {layer_key(8, 0), layer_key(8, 24)} and st.drawn_source(908) == layer_key(8, 0),
      "Metal1 is computed from 8/0 and 8/24, drawn on 8/0")
check(st.derived_keys_of(8, 0) == [908] and st.derived_keys_of(8, 24) == [908] and st.derived_keys_of(8, 2) == []
      and st.derived_keys_of(5, 0) == [], "a shape on 8/0 (or 8/24) belongs to Metal1; 8/2 and the RS operands to none")


def um(x0, y0, x1, y1):
    return pya.DBox(x0, y0, x1, y1).to_itype(0.001)


# a 200 x 200 ring frame on 8/0, 20 wide, cut by slits on 8/24 in its left and right sides: two U-shaped pieces;
# a Metal2 pad on the upper piece with 9 vias; a shape on 8/2 (no Metal1)
ly = pya.Layout()
ly.dbu = 0.001
top = ly.create_cell("TOP")
frame = pya.Region(um(0, 0, 200, 200)) - pya.Region(um(20, 20, 180, 180))
top.shapes(ly.layer(8, 0)).insert(frame)
top.shapes(ly.layer(8, 24)).insert(um(-5, 98, 25, 102))
top.shapes(ly.layer(8, 24)).insert(um(175, 98, 205, 102))
top.shapes(ly.layer(10, 0)).insert(um(90, 182, 110, 198))
for i in range(3):
    for j in range(3):
        top.shapes(ly.layer(19, 0)).insert(um(94 + 5 * i, 186 + 4 * j, 96 + 5 * i, 188 + 4 * j))
top.shapes(ly.layer(8, 2)).insert(um(100, 5, 110, 15))

m1 = region(ly, top, st, 908)
check(m1.count() == 2, f"Metal1 = 8/0 NOT 8/24: {m1.count()} pieces")
check(polygon_at(ly, top, st, 908, um(10, 100, 10, 100).center()) is None, "no Metal1 in the slit")
check(polygon_at(ly, top, st, 908, um(10, 50, 10, 50).center()) is not None, "Metal1 in the lower piece")
clipped = region(ly, top, st, 908, um(0, 0, 100, 100))
check(clipped.count() == 1 and clipped.bbox() == um(0, 0, 100, 98), f"computed inside a box: {clipped.bbox()}")

# ground: a mark on the lower piece is that piece only, the slits separate it from the upper one
ground = check_ground(ly, top, st, None, [(908, um(100, 10, 100, 10).center())])
check(set(ground.net) == {908} and ground.net[908].count() == 1 and ground.net[908].bbox() == um(0, 0, 200, 98),
      f"ground: the lower piece, {ground.net[908].bbox() if 908 in ground.net else None}")
check(ground.other_polygons == 2, f"other metal: the upper piece and the Metal2 pad ({ground.other_polygons})")
# a mark on the Metal2 pad reaches the upper Metal1 piece through Via1
ground = check_ground(ly, top, st, None, [(10, um(100, 190, 100, 190).center())])
check(set(ground.net) == {908, 10} and ground.net[908].bbox() == um(0, 102, 200, 200),
      "a mark on the Metal2 pad: the upper Metal1 piece, through the vias")

# ground marks from the GUI functions: a click on the frame, a selected 8/0 shape
seeds_before = gui.ground_seeds(ly)
names = gui.mark_ground_at(ly, top, st, um(100, 10, 100, 10).center())
check(names == ["Metal1"] and (908, um(100, 10, 100, 10).center()) in gui.ground_seeds(ly),
      f"a click on the 8/0 frame marks Metal1: {names}")
check(gui.metals_at_point(ly, top, st, um(10, 100, 10, 100).center()) == [], "a click in the slit marks nothing")
removed = gui.unmark_ground_at(ly, top, st, um(150, 10, 150, 10).center())
check(removed == ["Metal1"] and gui.ground_seeds(ly) == seeds_before, "a second click on the same piece unmarks it")

# the EM Port tool on Metal1: its edge, and the metals at a port
found = edge_at(ly, top, st, um(100, 20, 100, 20).center(), round(1 / ly.dbu))
check(found is not None and found[0] == "Metal1", f"the frame's inner edge is a Metal1 edge: {found and found[0]}")
found = edge_at(ly, top, st, um(100, 20, 100, 20).center(), round(1 / ly.dbu), layers={layer_key(8, 0), 8})
check(found is not None and found[0] == "Metal1", "with 8/0 visible, Metal1 is searched")
found = edge_at(ly, top, st, um(100, 20, 100, 20).center(), round(1 / ly.dbu), layers={10})
check(found is None, "with only Metal2 visible, no Metal1 edge")
check(metals_at(ly, top, st, um(95, 185, 95, 185)) == ["Metal2", "Metal1"], "Metal2 and Metal1 at the pad")

# the export writes the operands, gds2palace computes Metal1
result = export_flat(ly, top, st, os.path.join(OUT, "derived_em.gds"))
check({(8, 0), (8, 24), (10, 0), (19, 0)} <= set(result.kept) and (8, 2) not in result.kept,
      f"kept: {sorted(result.kept)}")

# the clean-up tools work on Metal1's drawn layer 8/0, never on the slits (8/24)
from klayout_em_export.density import fill_and_merge, merged_layers
from klayout_em_export.dummyfill import fill_layers, find_fill, remove_dummy_fill

check(st.metal_sources(908) == {layer_key(8, 0)}, f"Metal1's metal is drawn on 8/0: {st.metal_sources(908)}")
check(st.derived_metal_sources() == {layer_key(8, 0): [908]}, "8/0 is the drawn layer of Metal1, not of RS")
check(layer_key(8, 0) in fill_layers(st) and layer_key(8, 24) not in fill_layers(st), "fill searched on 8/0")
check(layer_key(8, 0) in merged_layers(st) and layer_key(8, 24) not in merged_layers(st)
      and 5 not in merged_layers(st), "8/0 merged, not the slits nor the resistor's operands")


def fill_layout():
    """The frame and pad above, plus: 30 floating 2x2 tiles on 8/0 (fill), 30 on 8/22 (fill on another datatype),
    30 slits 1x1 on 8/24 off the metal (repeated, floating: but no fill, they are slits), one tile with a Via1 to a
    Metal2 tile (not floating), and a 160 x 160 cheesed plate on 8/0 with 25 holes of 2 x 2 (density holes)."""
    ly = pya.Layout()
    ly.dbu = 0.001
    top = ly.create_cell("TOP")
    top.shapes(ly.layer(8, 0)).insert(frame)
    top.shapes(ly.layer(8, 24)).insert(um(-5, 98, 25, 102))
    top.shapes(ly.layer(8, 24)).insert(um(175, 98, 205, 102))
    for i in range(30):
        top.shapes(ly.layer(8, 0)).insert(um(300 + 5 * i, 0, 302 + 5 * i, 2))
        top.shapes(ly.layer(8, 22)).insert(um(300 + 5 * i, 10, 302 + 5 * i, 12))
        top.shapes(ly.layer(8, 24)).insert(um(300 + 5 * i, 20, 301 + 5 * i, 21))
    top.shapes(ly.layer(8, 0)).insert(um(300, 30, 302, 32))       # same size as the fill, but with a via
    top.shapes(ly.layer(19, 0)).insert(um(300.5, 30.5, 301.5, 31.5))
    top.shapes(ly.layer(10, 0)).insert(um(300, 30, 302, 32))
    plate = pya.Region(um(0, 300, 160, 460))
    for i in range(5):
        for j in range(5):
            plate -= pya.Region(um(20 + 30 * i, 320 + 30 * j, 22 + 30 * i, 322 + 30 * j))
    top.shapes(ly.layer(8, 0)).insert(plate)
    return ly, top


ly2, top2 = fill_layout()
fill = find_fill(ly2, top2, st)
check(set(fill) == {(8, 0), (8, 22)}, f"fill found on 8/0 and 8/22, not on the slits 8/24: {sorted(fill)}")
check(fill.get((8, 0), pya.Region()).count() == 30, f"30 tiles on 8/0, not the one with a via: "
      f"{fill.get((8, 0), pya.Region()).count()}")
removed, _ = remove_dummy_fill(ly2, top2, st)
check(removed == {(8, 0): 30, (8, 22): 30}, f"removed: {removed}")
check(pya.Region(top2.begin_shapes_rec(ly2.layer(8, 24))).count() == 32, "the slits stay")

result, _ = fill_and_merge(ly2, top2, st)
check("Metal1 (8/0)" in result and result["Metal1 (8/0)"].filled == 25,
      f"density holes of 8/0 filled: {[(n, r.filled) for n, r in result.items()]}")
plate_after = pya.Region(top2.begin_shapes_rec(ly2.layer(8, 0))).interacting(pya.Region(um(1, 301, 2, 302)))
check(plate_after.count() == 1 and all(p.holes() == 0 for p in plate_after.each()), "the plate has no holes left")
m1_after = region(ly2, top2, st, 908, um(-10, -10, 210, 210))
check(m1_after.count() == 2, f"the slits still cut Metal1 in two: {m1_after.count()}")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
