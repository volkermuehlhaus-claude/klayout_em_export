# Batch test (KLayout -z -nc -rx -r): a stackup whose layers name their GDS datatype (stackup format 3.2), with a
# metal and its via on one layer number (M1 on 68/20, V1 on 68/44, M2 on 69/20), as in sky130. The export keeps each
# layer on its datatype; ground, nets, shorts, port proposals at the region edge, net labels, the EM Port tool's edge
# search, Remove Dummy Fill, Fill Density Holes and Merge Metal, ground marks and Export Selection read the same
# shapes as gds2palace. A layer without a Datatype follows the export's datatypes as before. No PDK needed.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
import pya
from klayout_em_export import tech
from klayout_em_export.boundary import find_crossings
from klayout_em_export.connectivity import check_ground, net_labels, port_net_names, port_nets, wiring
from klayout_em_export.density import fill_and_merge
from klayout_em_export.dummyfill import fill_layers, remove_dummy_fill
from klayout_em_export.export import export_flat
from klayout_em_export.locate import drawn_metals, edge_at
from klayout_em_export.ports import PROP_KEY, PortSettings, collect_ports
from klayout_em_export.selection import Selection
from klayout_em_export.stackup import Stackup, StackupError, find_layer, key_text, layer_key, split_key

OUT = os.environ.get("OUT", ".")
os.makedirs(OUT, exist_ok=True)
failed = []


def check(ok, text):
    print(("ok    " if ok else "FAIL  ") + text)
    if not ok:
        failed.append(text)


# ---------- the stackup ----------
XML = '''<?xml version="1.0" encoding="UTF-8"?>
<Stackup schemaVersion="3.2">
  <Materials>
    <Material Name="Cu" Type="Conductor" Conductivity="5.8e7" />
    <Material Name="Ox" Type="Dielectric" Permittivity="4" />
  </Materials>
  <ELayers LengthUnit="um">
    <Dielectrics>
      <Dielectric Name="Box" Material="Ox" Zmin="0" Zmax="10" Boundary="301" BoundaryDatatype="5" />
    </Dielectrics>
    <Layers>
      <Layer Name="M2" Type="conductor" Material="Cu" Layer="69" Datatype="20" Zmin="3" Zmax="4" />
      <Layer Name="V1" Type="via" Material="Cu" Layer="68" Datatype="44" Zmin="2" Zmax="3" />
      <Layer Name="M1" Type="conductor" Material="Cu" Layer="68" Datatype="20" Zmin="1" Zmax="2" />
      <Layer Name="M0" Type="conductor" Material="Cu" Layer="71" Zmin="-1" Zmax="0" />
      <Layer Name="MD" Type="conductor" Material="Cu" Layer="310" Zmin="6" Zmax="7" />
    </Layers>
    <DerivedLayers>
      <DerivedLayer Name="MD" Layer="310" Operation="OR">
        <Operand Layer="70" Datatype="7" />
        <Operand Layer="72" />
      </DerivedLayer>
    </DerivedLayers>
  </ELayers>
</Stackup>'''

path = os.path.join(OUT, "datatype_stackup.xml")
open(path, "w").write(XML)
st = Stackup(path)
M1, V1, M2 = layer_key(68, 20), layer_key(68, 44), layer_key(69, 20)
check(M1 == 10006800020 and split_key(M1) == (68, 20) and key_text(M1) == "68/20", "layer keys as gds2palace's layer id")
check(layer_key(71) == 71 and split_key(71) == (71, None) and key_text(71) == "71", "a layer without Datatype: its number")
check([(l.name, l.key) for l in st.layers if l.name in ("M1", "V1", "M2", "M0")] ==
      [("M2", M2), ("V1", V1), ("M1", M1), ("M0", 71)], "each stackup layer has its key")
check(st.datatypes == {68: {20, 44}, 69: {20}, 70: {7}, 301: {5}} and st.plain == {71, 72}, "datatypes named")
check(st.reads(68, 20) and st.reads(68, 44) and not st.reads(68, 0) and st.reads(71, 0) and not st.reads(71, 9),
      "what the model reads")
check(st.key_of(68, 20) == M1 and st.key_of(68, 44) == V1 and st.key_of(68, 0) is None and st.key_of(71, 0) == 71
      and st.key_of(71, 5) is None, "key_of: the stackup layer read from a layer/datatype")
metals, connections = wiring(st)
check(metals == {M2: "M2", M1: "M1", 71: "M0", 310: "MD"} or metals == {M2: "M2", M1: "M1", 71: "M0"},
      f"traced metals by key: { {key_text(k): v for k, v in metals.items()} }")
check(connections == [(V1, M1, M2)], "the via on 68/44 connects M1 (68/20) and M2 (69/20)")
check(drawn_metals(st) == [("M2", M2), ("M1", M1), ("M0", 71)], "drawn metals by key, top first")
check(fill_layers(st) == sorted([M1, M2, 71]), "metals searched for fill, not the via on 68/44")
bad = os.path.join(OUT, "bad_stackup.xml")
open(bad, "w").write(XML.replace('Datatype="20" Zmin="3"', 'Datatype="=dt" Zmin="3"'))
try:
    Stackup(bad)
    check(False, "an expression as Datatype is refused")
except StackupError as e:
    check("Datatype" in str(e), "an expression as Datatype is refused")


# ---------- the layout ----------
def um(x0, y0, x1, y1):
    return pya.DBox(x0, y0, x1, y1).to_itype(0.001)


def build():
    """M1 plane on 68/20; an M2 line on 69/20 with via ports at both ends; an M2 pad tied to the plane by a 5 x 5 via
    array on 68/44; 25 floating M2 fill tiles; a label on the line (69/16); shapes on 68/0 and 69/0 that the model
    does not read (one of them under the line, to catch a lookup on datatype 0)."""
    ly = pya.Layout()
    ly.dbu = 0.001
    top = ly.create_cell("TOP")
    s = lambda layer, datatype: top.shapes(ly.layer(layer, datatype))
    s(68, 20).insert(um(0, 0, 200, 100))
    s(69, 20).insert(um(20, 45, 180, 55))
    s(69, 20).insert(um(90, 70, 110, 90))
    for i in range(5):
        for j in range(5):
            s(68, 44).insert(um(92 + 3 * i, 72 + 3 * j, 93 + 3 * i, 73 + 3 * j))
            s(69, 20).insert(um(10 + 5 * i, 10 + 5 * j, 12 + 5 * i, 12 + 5 * j))
    s(68, 0).insert(um(0, 0, 200, 100))
    s(69, 0).insert(um(20, 45, 180, 55))
    s(69, 16).insert(pya.Text("RF", pya.Trans(um(100, 50, 100, 50).center())))
    for number, x in ((201, 20), (202, 180)):
        s(number, 0).insert(um(x, 45, x, 55), ly.properties_id([[PROP_KEY, PortSettings("Z", "M1", "M2").encode()]]))
    return ly, top


ly, top = build()
ports = collect_ports(ly, top, stackup=st)
check(sorted(p.number for p in ports.values()) == [1, 2], "two via ports")

# ground, nets, shorts: from the via ports, through the vias on 68/44
ground = check_ground(ly, top, st, None, (), ports)
check(set(ground.metals) == {M1, M2}, f"traced metal: {sorted(key_text(k) for k in ground.metals)}")
check(ground.metals[M1].count() == 1 and ground.metals[M2].count() == 27,
      "M1 is the plane only (not the 68/0 copy), M2 the line, the pad and the tiles")
check(V1 in ground.vias and not ground.vias[V1].is_empty(), "the via array becomes a via block")
check("found from the via ports" in ground.source and ground.ports == [1, 2] and ground.shorted == [],
      f"ground: {ground.source}; ports reaching it {ground.ports}; shorted {ground.shorted}")
check(set(ground.net) == {M1, M2} and ground.net[M2].count() == 1,
      "the ground net: the plane, and through the vias the pad on M2 (not the line, not the tiles)")
check(ground.net[M2].bbox() == um(90, 70, 110, 90), "the pad is the M2 part of the ground")

# net labels: the text on 69/16 names the line's net, the ports' signal end
shapes = {}
nets = port_nets(ports, ground, shapes)
labels = net_labels(ly, top, set(ground.metals), None)
check([(t, key_text(k)) for t, _, k in labels] == [("RF", "69/20")], f"labels: {[(t, key_text(k)) for t, _, k in labels]}")
names = port_net_names(ports, nets, shapes, labels)
check(sorted(names.values()) == ["RF", "RF"], f"both ports are on the labelled net: {names}")
check({nets[layer][2] for layer in nets} == {"M2"}, "the signal end of both ports is M2")

# ports at the region edge: the box cuts the line on M2; ground at the cut is M1
box = um(50, 0, 150, 100)
# the ports lie outside the box: the ground is marked, on the M1 plane inside it
crossings = find_crossings(ly, top, st, box, check_ground(ly, top, st, box, [(M1, um(100, 20, 100, 20).center())], ports))
signal = [c for c in crossings if c.needs_port]
check(len(signal) == 2 and all(c.name == "M2" and c.layer == M2 and c.ground_layer == (M1, "M1") for c in signal),
      f"two port proposals on the M2 line, to M1: {[(c.side, c.name, c.ground_layer) for c in signal]}")

# the EM Port tool: the metal edge under a click
found = edge_at(ly, top, st, um(60, 55, 60, 55).center(), round(1 / ly.dbu))
check(found is not None and found[0] == "M2", f"edge at the line's upper edge: {found and found[0]}")
found = edge_at(ly, top, st, um(60, 55, 60, 55).center(), round(1 / ly.dbu), layers={M1})
check(found is None, "only M1 visible: no M1 edge there (the 69/0 copy does not count)")

# ground marks: a selected shape is mapped to its stackup layer by layer and datatype
check(st.key_of(68, 20) in metals and st.key_of(69, 0) is None, "a mark on 68/20 counts, one on 69/0 does not")
marked = check_ground(ly, top, st, None, [(M2, um(100, 80, 100, 80).center())], ports)
check(marked.pieces == 1 and set(marked.net) == {M1, M2}, "a ground mark on the M2 pad finds the plane through the vias")

# Export Selection: the vias that connect two selected metals are added, on their datatype
selection = Selection(ly, top)
for layer, datatype in ((68, 20), (69, 20)):
    li = ly.find_layer(layer, datatype)
    for shape in top.shapes(li).each():
        if shape.bbox().overlaps(um(85, 65, 115, 95)) or (layer, datatype) == (68, 20):
            selection.add_shape(shape, li, pya.ICplxTrans())
completed = selection.completed(st)
check(completed.added_vias == {V1: 25} and (68, 44) in completed.regions, f"vias added: {completed.added_vias}")

# Remove Dummy Fill: the 25 floating tiles on 69/20 go, the 25 vias on 68/44 stay
removed, cells = remove_dummy_fill(ly, top, st)
check(removed.get((69, 20)) == 25, f"fill removed: {removed}")
check((68, 44) not in removed and top.shapes(ly.find_layer(68, 44)).size() == 25, "the via array on 68/44 stays")
check(top.shapes(ly.find_layer(69, 20)).size() == 2, "the line and the pad stay")

# Fill Density Holes and Merge Metal: on the layer's datatype
ly2, top2 = build()
top2.shapes(ly2.layer(68, 20)).insert(um(0, 0, 100, 100))         # two overlapping M1 pieces: merged into one
before_68_0 = top2.shapes(ly2.find_layer(68, 0)).size()
result, moved = fill_and_merge(ly2, top2, st)
check("M1" in result and top2.shapes(ly2.find_layer(68, 20)).size() == 1, "M1 (68/20) merged")
check(top2.shapes(ly2.find_layer(68, 0)).size() == before_68_0 and top2.shapes(ly2.find_layer(68, 44)).size() == 25,
      "68/0 and the vias on 68/44 untouched")

# the export keeps each layer on its datatype
gds = os.path.join(OUT, "datatype_em.gds")
ly3, top3 = build()
result = export_flat(ly3, top3, st, gds)
check({(68, 20), (68, 44), (69, 20), (201, 0), (202, 0)} <= set(result.kept) and (68, 0) not in result.kept
      and (69, 0) not in result.kept, f"kept: {sorted(result.kept)}")
check(find_layer(ly3, M1) == ly3.find_layer(68, 20) and find_layer(ly3, 71) == ly3.find_layer(71, 0),
      "find_layer: a key's own datatype, else datatype 0")

# a stackup without Datatype: keys are the layer numbers, as before
plain = os.path.join(OUT, "plain_stackup.xml")
open(plain, "w").write(XML.replace(' Datatype="20"', "").replace(' Datatype="44"', "").replace(' Datatype="7"', "")
                       .replace(' BoundaryDatatype="5"', "").replace('Layer="68" Zmin="2"', 'Layer="67" Zmin="2"'))
sp = Stackup(plain)
check([l.key for l in sp.layers] == [l.layer for l in sp.layers] and sp.datatypes == {},
      "without Datatype every key is the layer number")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
