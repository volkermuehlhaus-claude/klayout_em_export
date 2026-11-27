# Batch test (KLayout -z -nc -rx -r): a stackup whose layers name their GDS datatype (stackup format 3.2). The export
# keeps a stackup layer on the datatype the stackup names, whatever the export's datatypes are, as gds2palace reads
# it; a layer without a Datatype follows the export's datatypes as before. The stackup says what the plug-in's checks
# do not cover. No PDK needed.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
import pya
from klayout_em_export.export import export_flat
from klayout_em_export.stackup import Stackup, StackupError

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
      <Dielectric Name="Box" Material="Ox" Zmin="0" Zmax="10" Boundary="301" BoundaryDatatype="5" />
    </Dielectrics>
    <Layers>
      <Layer Name="M1" Type="conductor" Material="Cu" Layer="68" Datatype="20" Zmin="1" Zmax="2" />
      <Layer Name="V1" Type="via" Material="Cu" Layer="68" Datatype="44" Zmin="2" Zmax="3" />
      <Layer Name="M2" Type="conductor" Material="Cu" Layer="69" Zmin="3" Zmax="4" />
      <Layer Name="MD" Type="conductor" Material="Cu" Layer="310" Zmin="6" Zmax="7" />
    </Layers>
    <DerivedLayers>
      <DerivedLayer Name="MD" Layer="310" Operation="OR">
        <Operand Layer="70" Datatype="7" />
        <Operand Layer="71" />
      </DerivedLayer>
    </DerivedLayers>
  </ELayers>
</Stackup>'''

path = os.path.join(OUT, "datatype_stackup.xml")
open(path, "w").write(XML)
st = Stackup(path)
check(st.datatypes == {68: {20, 44}, 70: {7}, 301: {5}}, f"datatypes named by the stackup: {st.datatypes}")
check(st.plain == {69, 71}, f"layers read from the export's datatypes: {sorted(st.plain)}")
check(st.reads(68, 20) and st.reads(68, 44) and not st.reads(68, 0) and not st.reads(68, 5),
      "68: only the two named datatypes")
check(st.reads(69, 0) and not st.reads(69, 9) and st.reads(69, 9, purposes=(0, 9)), "69: the export's datatypes")
check(st.reads(70, 7) and not st.reads(70, 0) and st.reads(71, 0), "operands of a derived layer")
check(st.reads(301, 5) and not st.reads(301, 0), "the dielectric's boundary datatype")
note = st.datatype_note()
check(note and "68/20, 68/44, 70/7, 301/5" in note and "datatype 0 only" in note, "the stackup says what is not covered")

plain = os.path.join(OUT, "plain_stackup.xml")
open(plain, "w").write(XML.replace(' Datatype="20"', "").replace(' Datatype="44"', "").replace(' Datatype="7"', "")
                       .replace(' BoundaryDatatype="5"', ""))
check(Stackup(plain).datatype_note() is None and Stackup(plain).datatypes == {}, "no note without a Datatype")
bad = os.path.join(OUT, "bad_stackup.xml")
open(bad, "w").write(XML.replace('Datatype="20"', 'Datatype="=dt"'))
try:
    Stackup(bad)
    check(False, "an expression as Datatype is refused")
except StackupError as e:
    check("Datatype" in str(e), "an expression as Datatype is refused")

# layout: every stackup layer number on the named datatype and on others
ly = pya.Layout()
ly.dbu = 0.001
top = ly.create_cell("TOP")
shapes = {(68, 20): 2, (68, 44): 3, (68, 0): 1, (68, 5): 1, (69, 0): 1, (69, 9): 1, (70, 7): 1, (70, 0): 1,
          (71, 0): 1, (301, 5): 1, (301, 0): 1, (201, 0): 1, (12, 0): 1}
x = 0
for (layer, datatype), count in shapes.items():
    for _ in range(count):
        top.shapes(ly.layer(layer, datatype)).insert(pya.Box(x, 0, x + 1000, 1000))
        x += 3000

gds = os.path.join(OUT, "datatype_em.gds")
result = export_flat(ly, top, st, gds)
check(set(result.kept) == {(68, 20), (68, 44), (69, 0), (70, 7), (71, 0), (301, 5), (201, 0)},
      f"kept: {sorted(result.kept)}")
check(result.kept[(68, 20)] == 2 and result.kept[(68, 44)] == 3, "metal and via on one layer number stay apart")
check(set(result.dropped) == {(68, 0), (68, 5), (69, 9), (70, 0), (301, 0), (12, 0)}, f"dropped: {sorted(result.dropped)}")
back = pya.Layout()
back.read(gds)
written = sorted((back.get_info(li).layer, back.get_info(li).datatype) for li in back.layer_indexes()
                 if not back.top_cell().shapes(li).is_empty())
check(written == sorted(result.kept), f"in the file: {written}")

result = export_flat(ly, top, st, os.path.join(OUT, "datatype_em9.gds"), purposes=(0, 9))
check((69, 9) in result.kept and (68, 0) not in result.kept and (68, 20) in result.kept,
      "the export's datatypes apply to the layers without a Datatype only")

result = export_flat(ly, top, Stackup(plain), os.path.join(OUT, "plain_em.gds"))
check(set(result.kept) == {(68, 0), (69, 0), (70, 0), (71, 0), (301, 0), (201, 0)},
      f"without Datatype as before: {sorted(result.kept)}")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
