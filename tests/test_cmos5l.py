# Batch test (KLayout -z -nc -rx -r): IHP SG13CMOS5L with its own PDK (ihp-sg13cmos5l, KLayout technology
# sg13cmos5l), not SG13G2's. The CMOS5L library is also called SG13_dev, and its MOSFET and resistor pcells are SG13G2's
# code (symlinks in IHP-Open-PDK); the process has no npn, no Metal5/TopMetal2 and no MIM. The MOSFET layout of
# test_mosfets.py (t1_test.gds: nmos, pmos, rfnmos, wired), read as a CMOS5L layout so that its pcells come from the
# CMOS5L library, plus one rsil, rppd, rhigh, moscap_n, moscap_p and SVaricap: the technology chosen, the devices and
# their terminals (also from the geometry, without the pins' name properties), the replacement by ports, the EM export,
# the thermal export with the SG13CMOS5L stackup and the circuit wrapper's lines for the capacitors. Needs
# ihp-sg13cmos5l in the PDK folder (tests/setup_pdk.sh), skipped without.
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testpaths import GDS2PALACE, TESTS_DIR, layout_file, out_dir

import pya
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.join(TESTS_DIR, "..", "python"))   # not via salt here
from pdk_env import load_pdk
from klayout_em_export import tech
from klayout_em_export.devices import device_shapes, find_devices, mark_replaced, replace
from klayout_em_export.export import export_flat
from klayout_em_export.pipeline import NoUndo   # a standalone layout in batch mode has no undo manager
from klayout_em_export.ports import collect_ports, export_numbering
from klayout_em_export.stackup import Stackup
from klayout_em_export.thermal import export_thermal

failed = []


def check(ok, text):
    print("ok   " if ok else "FAIL ", text)
    if not ok:
        failed.append(text)


lib = load_pdk("sg13cmos5l")
check(lib is not None and lib.technology == "sg13cmos5l", f"SG13_dev of sg13cmos5l: {lib and lib.description}")
st = Stackup(os.path.join(GDS2PALACE, "XML_stackup", "latest", "IHP", "SG13CMOS5L_200um.xml"))
OUT = out_dir("cmos5l")
os.makedirs(OUT, exist_ok=True)
RESISTORS = ("rsil", "rppd", "rhigh")
CAPACITORS = {"moscap_n": ["G", "SUB"], "moscap_p": ["G", "NW"], "SVaricap": ["G1", "G2", "W"]}
# t1_test.gds with SG13G2 (test_mosfets.py): the same devices, parameters and terminals are expected
T1_DEVICES = [("nmos", "2u", "1"), ("nmos", "2u", "1"), ("nmos", "2u", "1"), ("nmos", "4u", "4"), ("pmos", "2u", "2"),
              ("rfnmos", "4u", "2")]


def build():
    """t1_test.gds read as a CMOS5L layout, with a resistor and a capacitor of each kind next to it."""
    ly = pya.Layout()
    ly.technology_name = "sg13cmos5l"
    ly.read(layout_file("t1_test.gds"))
    top = ly.cell("TOP")
    for i, name in enumerate(RESISTORS + tuple(CAPACITORS)):
        pcell = ly.create_cell(name, "SG13_dev", {})
        top.insert(pya.DCellInstArray(pcell.cell_index(), pya.DTrans(20.0 * i, -30.0)))
    return ly, top


ly, top = build()
devices, unknown = find_devices(ly, top, st)
libraries = {ly.cell(d.cell_index).library().technology for d in devices if ly.cell(d.cell_index).library()}
check(libraries == {"sg13cmos5l"}, f"the devices are CMOS5L library cells: {libraries}")
technology, reason = tech.for_layout(ly)
check(technology.NAME == "ihp_sg13", f"technology {technology.NAME} ({reason})")
for d in sorted(devices, key=lambda d: (d.trans.disp.y, d.trans.disp.x)):
    print(f"{d.pcell:7s} {d.params} problems {d.problems} terminals "
          f"{ {t: (layer, len(boxes)) for t, (layer, boxes) in sorted(d.terminals.items())} }")
check(not unknown, f"no unknown devices: {unknown}")
found = sorted((d.pcell, d.params.get("w"), d.params.get("ng")) for d in devices
               if d.pcell not in RESISTORS and d.pcell not in CAPACITORS)
check(found == sorted(T1_DEVICES), f"the MOSFETs of t1_test.gds, as with SG13G2: {found}")
check(sorted(d.pcell for d in devices if d.pcell in RESISTORS) == sorted(RESISTORS), "one resistor of each kind")
for d in devices:
    check(not d.problems, f"{d.id}: no problems {d.problems}")
check(all({"D", "G", "S"} <= set(d.terminals) for d in devices if d.pcell not in RESISTORS + tuple(CAPACITORS)),
      "each MOSFET has drain, gate and source")
check(all(sorted(d.terminals) == ["MINUS", "PLUS"] for d in devices if d.pcell in RESISTORS),
      "each resistor has PLUS and MINUS")
terminals_of = {d.pcell: sorted(d.terminals) for d in devices if d.pcell in CAPACITORS}
check(terminals_of == {k: sorted(v) for k, v in CAPACITORS.items()}, f"the capacitors' terminals: {terminals_of}")
metal1 = st.layer("Metal1").layer
check(all(layer == metal1 for d in devices for layer, _ in d.terminals.values()), "all terminals on Metal1")

# ---- the capacitors without the pins' name properties (IHP-Open-PDK before October 2026): the
# same terminals from the gate poly under the pins
plain_ly, plain_top = build()
def named_pins(ly):
    return sum(1 for c in ly.each_cell() for li in ly.layer_indexes() for s in c.shapes(li).each()
               if s.prop_id and s.property("PIN_INFO__TERM_NAME"))


before = named_pins(plain_ly)
for c in plain_ly.each_cell():
    for li in plain_ly.layer_indexes():
        for s in [s for s in c.shapes(li).each() if s.prop_id]:
            c.shapes(li).erase(s)
check(before > 0 and named_pins(plain_ly) == 0, f"name properties removed: {before} pin shapes had one")
plain = {d.pcell: {t: [str(b) for b in boxes] for t, (_, boxes) in d.terminals.items()}
         for d in find_devices(plain_ly, plain_top, st)[0] if d.pcell in CAPACITORS}
named = {d.pcell: {t: [str(b) for b in boxes] for t, (_, boxes) in d.terminals.items()}
         for d in devices if d.pcell in CAPACITORS}
check(plain == named, f"without name properties, the same capacitor terminals from the geometry: {plain}")

# ---- a static capacitor cell (a pcell saved without its pcell context): recognized, its terminals found, but not
# replaced, since its label gives no size for the PDK model
static_ly = pya.Layout()
static_ly.technology_name = "sg13cmos5l"
static_top = static_ly.create_cell("TOP")
static = static_ly.create_cell("moscap_n$7")
static.copy_tree(static_ly.create_cell("moscap_n", "SG13_dev", {}))
static_top.insert(pya.CellInstArray(static.cell_index(), pya.Trans()))
found_static = [d for d in find_devices(static_ly, static_top, st)[0] if d.id.startswith("moscap_n$7@")]
check(len(found_static) == 1 and sorted(found_static[0].terminals) == ["G", "SUB"]
      and any("static MOS capacitor" in p for p in found_static[0].problems),
      f"static moscap_n: {[(d.terminals.keys(), d.problems) for d in found_static]}")

# ---- the circuit wrapper: the capacitors' PDK models with their terminals in the model's order
sys.path.insert(0, os.path.join(TESTS_DIR, "..", "python", "klayout_em_export", "tech"))
import ihp_sg13_circuit as circuit
for d in devices:
    if d.pcell in CAPACITORS:
        term = {t: t.lower() for t in d.terminals}      # the device's own terminals, as the wrapper has them
        items, notes, kind = circuit.instantiate(1, d.id, d.pcell, d.params, term)
        print(d.pcell, items, notes, kind)
        _, _, model, nodes, values = items[0]
        want = {"moscap_n": ("sg13_moscap_n", ["g", "sub"], "moscap"), "moscap_p": ("sg13_moscap_p", ["g", "nw"], "moscap"),
                "SVaricap": ("sg13_hv_svaricap", ["g1", "w", "g2", "0"], "moshv")}[d.pcell]
        check((model, nodes, kind) == want and "w" in values and "l" in values,
              f"{d.pcell}: {model} {nodes} {values}, library {circuit.LIBRARIES[kind]}")

# ---- replaced by ports (resistors too), exported for EM with the CMOS5L stackup
ports_of = replace(NoUndo(), top, st, devices, include_resistors=True)
clean = [d for d in devices if not d.problems]
check(len(ports_of) == len(clean), f"every device without problems replaced: {len(ports_of)} of {len(clean)}")
again = mark_replaced(ly, top, find_devices(ly, top, st)[0])
ports = collect_ports(ly, top, stackup=st)
expected = sum(len(t) for t in ports_of.values())
check(len(ports) == expected, f"one via port per terminal: {len(ports)} of {expected}")
ref = st.layer("REF_FOR_TRANSISTOR").name
check(all(f"Metal1 -> {ref}" in str(p.settings) for p in ports.values()),
      f"each port from Metal1 to {ref}: {sorted({str(p.settings) for p in ports.values()})[:2]}")
gds = os.path.join(OUT, "cmos5l_em.gds")
export_flat(ly, top, st, gds, port_layers=export_numbering(ports), remove=device_shapes(ly, again, st))
out = pya.Layout()
out.read(gds)
written = {(out.get_info(li).layer, out.get_info(li).datatype) for li in out.layer_indexes()
           if not out.top_cell().bbox_per_layer(li).empty()}
allowed = {(n, 0) for n in st.gds_layers()} | {(n, 0) for n in range(201, 300)}
check(written <= allowed, f"only the stackup's layers and port layers in the EM export: {sorted(written - allowed)}")

# ---- thermal: one heat source per device in the stackup's heat target layers, resistor heads unheated
ly, top = build()
result = export_thermal(ly, top, st, os.path.join(OUT, "cmos5l_thermal.gds"), technology)
rows = json.load(open(result["thermalmap"]))["sources"]
print("sources:", [(r["pcell"], r["target_layer"], r["heat_area_from"], r["area_um2"], r["unheated_poly_um2"])
                   for r in rows])
check(len(rows) == len([d for d in devices if d.pcell not in CAPACITORS]),
      f"one heat source per device, none for the capacitors: {len(rows)}")
check(all(r["heat_area_from"] == ("bbox" if r["pcell"].startswith("rf") else "shapes") for r in rows),
      "heat areas from the PDK's shapes (rf MOSFETs have none: bounding box, as with SG13G2)")
check(all(r["target_layer"] == ("HEAT_RESISTOR" if r["pcell"] in RESISTORS else "HEAT_TRANSISTOR") for r in rows),
      "transistors in HEAT_TRANSISTOR, resistors in HEAT_RESISTOR")
check(all((r["unheated_poly_um2"] > 0) == (r["pcell"] in RESISTORS) for r in rows),
      "unheated poly heads for the resistors only")

print("all passed" if not failed else f"FAILED: {'; '.join(failed)}")
