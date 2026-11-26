# Batch test (KLayout -z -nc -rx -r): the net labels of the layout in the port map (net_name), which Create Circuit
# uses as pin names. The cascode has three labels in its top cell: Cas_in and Cas_out on TopMetal2.text (134/25) at
# the RF pads, Cas_Bias on Metal2.text (10/25) at the bias wire. Texts inside the device cells (pin names on 63/0)
# and the top cell's text on TEXT.drawing (sub!) name no net. Needs the PDK (tests/pdk_env.py).
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testpaths import STACKUP, TESTS_DIR, layout_file
import pya
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from pdk_env import load_pdk
from klayout_em_export import tech
from klayout_em_export.connectivity import check_ground, net_labels, port_net_names, port_nets
from klayout_em_export.locate import next_port_layer
from klayout_em_export.pipeline import export_em
from klayout_em_export.ports import PROP_KEY, PortSettings, collect_ports
from klayout_em_export.stackup import Stackup

OUT = os.environ.get("OUT", ".")
os.makedirs(OUT, exist_ok=True)
failed = []


def check(ok, text):
    print(("ok    " if ok else "FAIL  ") + text)
    if not ok:
        failed.append(text)


load_pdk()
st = Stackup(STACKUP)
ly = pya.Layout(); ly.technology_name = "sg13g2"
ly.read(layout_file("1_St_Core_v1_forEM.gds"))
cell = next(c for c in ly.top_cells() if c.name.startswith("Cascode"))
technology = tech.for_layout(ly)[0]
check(technology.NAME == "ihp_sg13", f"technology {technology.NAME}")

# a port at the Cas_Bias pin, as in run_cascode_export.py (Metal2 stub at the left cell edge)
bias_layer = next_port_layer(ly, cell)
cell.shapes(ly.layer(bias_layer, 0)).insert(pya.DBox(-29.205, 8.34, -29.205, 10.97).to_itype(ly.dbu),
                                            ly.properties_id([[PROP_KEY, PortSettings("Z", "Metal2", "Metal5").encode()]]))

# the labels that can name a net: on a traced metal's layer number, text or pin purpose, in the top cell only
ports = collect_ports(ly, cell, stackup=st)
ground = check_ground(ly, cell, st, None, (), ports)
labels = net_labels(ly, cell, set(ground.metals), technology.NET_LABEL_DATATYPES)
texts = sorted(text for text, _, _ in labels)
print("net labels:", [(text, layer) for text, _, layer in labels])
check(texts == ["Cas_Bias", "Cas_in", "Cas_out"], f"three net labels in the top cell: {texts}")
any_datatype = sorted(text for text, _, _ in net_labels(ly, cell, set(ground.metals), None))
check(any_datatype == texts, "no other texts on the metals' layer numbers in this layout")

# the export writes them into the port map
gds = os.path.join(OUT, "labels_em.gds")
if os.path.exists(gds.replace(".gds", ".simcfg")):
    os.remove(gds.replace(".gds", ".simcfg"))
pm = json.load(open(export_em(ly, cell, st, gds, technology)["portmap"]))
named = {row["layout_port"]: row["net_name"] for row in pm["ports"] if "net_name" in row}
pads = {row["layout_port"]: row.get("net_name") for row in pm["ports"] if "device" not in row}
print("ports that are no device terminals:", pads)
check(sorted(v for v in pads.values() if v) == ["Cas_Bias", "Cas_in", "Cas_out"],
      "the two RF pads and the bias port carry their net's label")
check(pads.get(bias_layer - 200) == "Cas_Bias", "the port at the bias wire is Cas_Bias")
by_net = {}
for row in pm["ports"]:
    if "net" in row:
        by_net.setdefault(row["net"], set()).add(row.get("net_name"))
check(all(len(names) == 1 for names in by_net.values()), "all ports of one net have the same name (or none)")
check(all("net_name" not in row for row in pm["ports"] if row.get("ground_net")), "the ground net has no label here")
check("net_name" in pm["note"], "the port map's note explains net_name")

# two different labels on one net: each port takes the nearest one
net_shapes = {}
nets = port_nets(ports, ground, net_shapes)
out_layer = next(layer for layer, port in ports.items() if named.get(port.number) == "Cas_out")
far = pya.Point(10**9, 10**9)
bbox = pya.Box()
for shape, trans, _ in ports[out_layer].items:
    bbox += shape.bbox().transformed(trans)
out_label = next(item for item in labels if item[0] == "Cas_out")
second = ("OTHER", out_label[1], out_label[2])          # at the same spot as Cas_out, so on the same net
names = port_net_names(ports, nets, net_shapes, labels + [second])
check(names[out_layer] == "Cas_out", "same distance: the first name in alphabetical order")
names = port_net_names(ports, nets, net_shapes, [l for l in labels if l[0] != "Cas_out"] + [second])
check(names[out_layer] == "OTHER", "a label on the net names it")
off_metal = ("NOWHERE", far, out_label[2])
names = port_net_names(ports, nets, net_shapes, labels + [off_metal])
check("NOWHERE" not in names.values(), "a label that sits on no metal names nothing")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
