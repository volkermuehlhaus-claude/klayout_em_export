# Batch test (KLayout -z -nc -rx -r, or plain Python): the pin names of Create Circuit's subcircuit
# (tools/spice_wrapper.py pin_names, build). A pin takes its net's label from the layout (port map: net_name); without
# one, or where the label can't be a node name of its own, it stays port<N>. Uses the cascode example's port map.
import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import spice_wrapper

failed = []


def check(ok, text):
    print(("ok    " if ok else "FAIL  ") + text)
    if not ok:
        failed.append(text)


def ports(*rows):
    """{port number: port map row}: (number, net_name or None[, device])."""
    out = {}
    for row in rows:
        r = {"port": row[0], "in_simcfg": True}
        if row[1] is not None:
            r["net_name"] = row[1]
        if len(row) > 2:
            r["device"], r["terminal"] = row[2], "C"
        out[row[0]] = r
    return out


names = spice_wrapper.pin_names(ports((1, "Cas_out"), (2, "Cas_in"), (3, "Cas_in", "npn"), (15, "Cas_Bias")))
check(names == {1: "Cas_out", 2: "Cas_in", 15: "Cas_Bias"}, f"labels become pin names, device ports are no pins: {names}")
names = spice_wrapper.pin_names(ports((1, None), (2, "")))
check(names == {1: "port1", 2: "port2"}, "no label: port<N>")
names = spice_wrapper.pin_names(ports((1, "VCC"), (2, "VCC"), (3, "vcc"), (4, "RF in")))
check(names == {1: "VCC_p1", 2: "VCC_p2", 3: "vcc_p3", 4: "RF_in"},
      f"the same name on two pins, also in other case: the port number is added; a blank becomes _: {names}")
names = spice_wrapper.pin_names(ports((1, "1"), (2, "2V5"), (3, "GND"), (4, "0"), (5, "port9"), (6, "n3"), (7, "---"),
                                      (8, "sub!")))
check(names == {1: "p_1", 2: "p_2V5", 3: "port3", 4: "p_0", 5: "port5", 6: "port6", 7: "port7", 8: "sub_"},
      f"a leading digit gets p_ (so 0 is not ground); gnd and the wrapper's own node names are not used: {names}")
names = spice_wrapper.pin_names(ports((1, "Cas_out"), (2, "Cas_in")), numbered=True)
check(names == {1: "port1", 2: "port2"}, "numbered pins on request")

# the cascode example: three pins, in the order of their port numbers
portmap = json.load(open(os.path.join(HERE, "..", "examples", "cascode", "em_result", "cascode_em_portmap.json")))
circuit = spice_wrapper.build(portmap, 15, False, "cascode")
check(circuit.pins == ["Cas_out", "Cas_in", "Cas_Bias"], f"cascode pins: {circuit.pins}")
check([(node, n) for node, n, _ in circuit.header] == [("Cas_out", 1), ("Cas_in", 2), ("Cas_Bias", 15)],
      "the header names each pin's port")
ties = [item[2:4] for item in circuit.items if item[0] == "L"]
check(("Cas_out", "n11") in ties and ("Cas_in", "n3") in ties and ("n6", "Cas_Bias") in ties,
      f"the DC ties use the pin names: {ties}")
check(circuit.em_nodes[0] == "Cas_out" and circuit.em_nodes[14] == "Cas_Bias" and circuit.em_nodes[2] == "n3",
      "the EM model's pins are in port order")
numbered = spice_wrapper.build(portmap, 15, False, "cascode", numbered_pins=True)
check(numbered.pins == ["port1", "port2", "port15"], "numbered pins as before")
old = json.loads(json.dumps(portmap))
for row in old["ports"]:
    row.pop("net_name", None)
check(spice_wrapper.build(old, 15, False, "cascode").pins == ["port1", "port2", "port15"],
      "a port map of an older export: port<N>")
blocked = spice_wrapper.build(portmap, 15, True, "cascode")
check(("C", "Cdc1", "Cas_out", "e1", "1u") in blocked.items, "DC blocks use the pin names too")

# xschem: the symbol's pins in the subcircuit's order, the include of the circuit file, the starter testbench
symbol, position = spice_wrapper.xschem_symbol(circuit, os.path.join("some", "folder", "cascode.cir"))
boxes = [line.split("name=")[1].split()[0] for line in symbol.splitlines() if line.startswith("B 5 ")]
check(boxes == circuit.pins, f"symbol pins in the subcircuit's order: {boxes}")
check("type=subcircuit" in symbol and 'format="@name @pinlist @symname"' in symbol, "a subcircuit symbol")
check("spice_sym_def=" in symbol and "abs_sym_path" in symbol and " cascode.cir])" in symbol and "some" not in symbol,
      "the symbol includes the circuit file from its own folder, without a fixed path")
check(position["Cas_out"][2] == 1 and position["Cas_in"][2] == -1 and position["Cas_Bias"][2] == -1,
      "pins with 'out' in the name on the right, the others on the left")
check(spice_wrapper.xschem_sides(["a", "b", "c"]) == (["a", "b"], ["c"]), "no 'out' pin: second half on the right")
testbench = spice_wrapper.xschem_testbench(circuit, "cascode.sym", position, "ngspice")
check("C {cascode.sym} 0 0 0 0 {name=x1}" in testbench, "the testbench places the symbol")
check(all(f"lab={pin}}}" in testbench for pin in circuit.pins), "a label at each pin")
check(".lib $::SG13G2_MODELS/cornerHBT.lib hbt_typ" in testbench and "cornerRES" not in testbench,
      "the model library of the device kinds used")
check("print v(Cas_out) v(Cas_in) v(Cas_Bias)" in testbench, "an operating point that prints the pin voltages")

print("FAILED: " + "; ".join(failed) if failed else "all passed")
