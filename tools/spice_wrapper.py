"""Circuit wrapper for an EM export with replaced devices: the EM model plus the PDK device models at the ports that
replaced them, as a subcircuit for ngspice, VACASK, Xyce or Spectre.

    python tools/spice_wrapper.py <export>_portmap.json <model>.sNp [-o <file>]
        [--simulator ngspice|vacask|xyce|spectre] [--em fit|snp] [--pdk <PDK folder, e.g. IHP-Open-PDK/ihp-sg13g2>]
        [--no-thermal-noise] [--numbered-pins] [--no-xschem]

The EM model goes in either way:
  fit   a lumped-element equivalent circuit made by snp2le (universal mode: vector fitted, passive), written next to
        the output as <name>_le.cir (ngspice, Xyce) or <name>_le.inc (VACASK). Needs a Python with snp2le
       . ngspice and VACASK can only use this. It carries the EM structure's thermal noise (snp2le --thermal-noise;
        without it, if snp2le cannot add it, with a note). Xyce gets snp2le's Xyce format (newer than snp2le 0.1.20 on
        PyPI); with an older snp2le its ngspice format without noisy=0, whose noise results are not valid.
  snp   the .sNp file itself, read by the simulator: Xyce (YLIN element) and Spectre (nport element).
Default: fit for ngspice and VACASK, snp for Xyce and Spectre.

Use the gds2palace result with its DC point (<model>_dc.sNp, from a sweep started at 0 Hz: gds2palace then simulates
two low frequencies, normally 10 MHz and 20 MHz, and extrapolates 0 Hz from them); snp2le pins the equivalent
circuit to that point.

The subcircuit's pins are the ports that belong to no device (pads, bias inputs, ...), in the order of their port
numbers. A pin is named after its net's label in the layout (port map: net_name, e.g. Cas_in), else port<N>; see
pin_names(). --numbered-pins names them all port<N>. Each device terminal is wired
straight to its port's pin of the EM model. In the EM model a device's ports end on the device's own floating
REF_FOR_TRANSISTOR patch, while the EM model references every port to ground: wiring the device directly grounds that
patch. This adds the patch's capacitance (a few fF per transistor) and changes the result slightly (cascode test:
S21 0.06 dB at 10 GHz, 0.4 dB at 200 GHz), against a much simpler netlist.

The export sets each via port's direction so that every via port has its signal metal on the same end (port map:
direction, signal_layer); a port map without them is from an older export, whose ports may be reversed: export again.

DC paths: a port measures a voltage difference, so the EM model does not fix the absolute potential of a device
whose ports end on its floating REF patch. The port map names each port's net (traced through the layout's vias at
the export); ports on one net are tied together, and to ground on the ground net, by 1 mH inductors: a short at DC,
open at GHz. The wires' DC resistance is not modelled. Without a 0 Hz point in the .sNp the EM model's DC is a guess
(it leaks tens of kOhm between nets): then every port also gets a 1 uF DC block, which keeps the EM model out of the
DC solution. The device's substrate/bulk pin, not part of the EM model, goes to ground (nmos, npn, resistors) or to
the source (pmos).

Model libraries (with --pdk, active lines, else commented): ngspice and Xyce from the PDK's libs.tech/ngspice or
libs.tech/xyce; VACASK includes the PDK's libraries by name, found through the PDK's .vacaskrc.toml (copy it next to
the testbench); Spectre gets commented include lines to adapt to your PDK.

The device models, their terminal order and the model libraries come from the technology named in the port map
(python/klayout_em_export/tech/<technology>_circuit.py; port maps without it are IHP SG13G2/SG13CMOS5L).
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from klayout_em_export import tech as technologies               # noqa: E402  (plain Python, no pya)


EM_DEFAULT = {"ngspice": "fit", "vacask": "fit", "xyce": "snp", "spectre": "snp"}
EM_ALLOWED = {"ngspice": ("fit",), "vacask": ("fit",), "xyce": ("snp", "fit"), "spectre": ("snp",)}
EXTENSION = {"ngspice": ".cir", "vacask": ".inc", "xyce": ".cir", "spectre": ".scs"}
VACASK_PRIMITIVES = ("resistor", "capacitor", "inductor", "vsource", "vccs", "cccs", "vcvs", "ccvs")
VACASK_MODULES = ("resistor", "capacitor", "inductor")      # loaded from VACASK's modules, the others are built in


def has_dc_point(snp):
    """True if the Touchstone file's first frequency is 0 Hz."""
    for line in open(snp):
        line = line.split("!")[0].strip()
        if line and not line.startswith("#") and not line.startswith("["):
            return float(line.split()[0]) == 0.0
    return False


def touchstone_ports(snp):
    m = re.search(r"\.s(\d+)p$", snp.lower())
    return int(m.group(1)) if m else None


def snp2le_formats():
    """The netlist dialects the installed snp2le writes (its convert --format choices), e.g. ['ngspice', 'vacask',
    'xyce', 'both', 'all']. The Xyce dialect is newer than snp2le 0.1.20 on PyPI, whose main branch has the same
    version number, so it is asked for, not inferred from the version."""
    result = subprocess.run([sys.executable, "-m", "snp2le", "-b", "convert", "--help"], capture_output=True, text=True)
    m = re.search(r"--format \{([^}]*)\}", result.stdout)
    return m.group(1).split(",") if m else []


def _run_snp2le(snp, out, fmt, thermal_noise):
    command = [sys.executable, "-m", "snp2le", "-b", "convert", snp, "--mode", "universal", "--format", fmt, "-o", out]
    if thermal_noise:
        command.append("--thermal-noise")
    result = subprocess.run(command, capture_output=True, text=True)
    report = [l for l in (result.stdout + result.stderr).splitlines() if "[" in l or "note" in l]
    return result.returncode == 0 and os.path.isfile(out), report, result


def equivalent_circuit(snp, out, fmt, thermal_noise=True):
    """Run snp2le (universal mode) and return (subcircuit name, pin count, notes) of the equivalent circuit it wrote.
    thermal_noise: the model carries the EM structure's thermal noise, kT(I - S S^H) at its ports (snp2le
    --thermal-noise); without it the model is noiseless, since its fit resistors are written noiseless. snp2le adds
    the noise only to a strictly passive model and refuses otherwise: then the model is made without it, with a note."""
    notes = []
    ok, report, result = _run_snp2le(snp, out, fmt, thermal_noise)
    if not ok and thermal_noise:
        print("\n".join(report))
        print("snp2le could not add the thermal noise (see above), the EM model is made without it")
        why = next((l.split("NOT added:", 1)[1].strip() for l in report if "NOT added:" in l), "see snp2le's output")
        notes.append(f"the EM model carries no thermal noise, snp2le could not add it ({why}): noise analyses miss "
                     "the EM structure's own noise")
        ok, report, result = _run_snp2le(snp, out, fmt, False)
    elif not thermal_noise:
        notes.append("the EM model is noiseless (made without thermal noise): noise analyses miss the EM structure's "
                     "own noise")
    print("\n".join(report))
    if not ok:
        sys.exit(f"snp2le failed:\n{result.stdout}\n{result.stderr}")
    for line in open(out):
        words = line.replace("(", " ( ").split()
        if words and words[0].lower() in (".subckt", "subckt"):
            pins = [w for w in words[2:] if w not in "()"]
            return words[1], len(pins), notes
    sys.exit(f"no subcircuit in {out}")


def vacask_private_models(path):
    """Rename the primitive models of snp2le's VACASK model to em_<type> (declared by the wrapper, so they cannot
    clash with the testbench's own declarations), and its ground GND to 0 (ground inside VACASK subcircuits)."""
    text = open(path).read()
    text = re.sub(r"^(\s*\S+\s*\([^)]*\)\s*)(" + "|".join(VACASK_PRIMITIVES) + r")\b", r"\1em_\2", text, flags=re.M)
    text = re.sub(r"\bGND\b", "0", text)
    open(path, "w").write(text)
    used = sorted(set(re.findall(r"\bem_(" + "|".join(VACASK_PRIMITIVES) + r")\b", text)))
    return used


def xyce_compatible(path):
    """For an snp2le without its Xyce dialect: its ngspice model marks the fit resistors noisy=0, which Xyce does not
    know: remove it. Xyce then adds those resistors' thermal noise, which belongs to the fit, not to the structure:
    noise results through the EM model are not valid then. snp2le's Xyce dialect writes them as noiseless
    conductances instead."""
    text = open(path).read()
    open(path, "w").write(re.sub(r"\s+noisy=0\b", "", text, flags=re.I))


class Circuit:
    """The wrapper independent of the simulator: pins, the EM model's pin nodes and the elements around it."""

    def __init__(self, name):
        self.name = name
        self.pins = []              # subcircuit pins (external ports)
        self.em_nodes = []          # node at each pin of the EM model, in port order
        # ("comment", text) | ("device", name, model, [nodes], {params}) | (R|L|C, name, a, b, value)
        self.items = []
        self.kinds = set()          # PDK library kinds used (hbt, mos, ...)
        self.tech = None            # the technology's circuit module (tech/<technology>_circuit.py)
        self.notes = []
        self.header = []            # (port number, layout port) of the pins


RESERVED_NODES = re.compile(r"(0|gnd|(n|e|port)\d+)$", re.I)     # ground, and this wrapper's own node names


def pin_names(ports, numbered=False):
    """{port number: pin name} of the ports that are no device terminals. A pin takes the label of its net in the
    layout (port map: net_name, from an export with klayout_em_export 0.5.0 or newer), e.g. Cas_in, so that a
    testbench reads like the schematic. Characters a node name can't have become "_"; a name that starts with a
    digit gets "p_" in front. Two pins with the same name (two pads on one net, or the same label on two nets) get
    "_p<port number>" behind it. Without a label, with a name that is the ground node or one of this wrapper's
    own nodes, or with numbered=True: port<N>."""
    pins = sorted(n for n, r in ports.items() if "device" not in r)
    names = {}
    for n in pins:
        label = re.sub(r"\W", "_", str(ports[n].get("net_name") or "").strip())
        if numbered or not label.strip("_"):
            continue
        if label[0].isdigit():
            label = "p_" + label
        if not RESERVED_NODES.match(label):
            names[n] = label
    count = {}
    for label in names.values():
        count[label.lower()] = count.get(label.lower(), 0) + 1      # ngspice does not tell upper from lower case
    names = {n: (label if count[label.lower()] == 1 else f"{label}_p{n}") for n, label in names.items()}
    return {n: names.get(n, f"port{n}") for n in pins}


def build(portmap, em_pins, dc_blocks, name, numbered_pins=False):
    """Circuit from the port map. em_pins: the EM model's pin count (= simulated ports). numbered_pins: the pins
    are port<N>, also where the port map has the net's label."""
    ports = {r["port"]: r for r in portmap["ports"] if r["in_simcfg"]}
    if len(ports) != em_pins:
        sys.exit(f"the port map has {len(ports)} simulated ports, the EM model {em_pins} pins")
    c = Circuit(name)
    try:
        c.tech = tech = technologies.load_circuit(portmap.get("technology") or technologies.PORTMAP_DEFAULT)
    except ValueError as e:
        sys.exit(f"port map: {e}")
    pins = pin_names(ports, numbered_pins)
    node = {n: (f"n{n}" if "device" in r else pins[n]) for n, r in ports.items()}
    c.pins = [node[n] for n in sorted(ports) if "device" not in ports[n]]
    c.header = [(node[n], n, ports[n]["layout_port"]) for n in sorted(ports) if "device" not in ports[n]]
    if any(r["settings"] and "signal_layer" not in r for r in ports.values()):
        c.notes.append("the port map has no signal layers (older export): via ports may be reversed, export again")
    terminals = {}                              # device id -> {terminal: node}
    for n, r in ports.items():
        if "device" in r:
            terminals.setdefault(r["device"], {})[r["terminal"]] = node[n]

    for k, (device_id, term) in enumerate(sorted(terminals.items()), start=1):
        info = portmap.get("devices", {}).get(device_id, {})
        pcell = info.get("pcell") or tech.pcell_of(device_id)
        ports_of = ", ".join(f"{r['terminal']} port {n}" for n, r in sorted(ports.items())
                             if r.get("device") == device_id)
        c.items.append(("comment", f"{pcell} {device_id} ({ports_of})"))
        items, notes, kind = tech.instantiate(k, device_id, pcell, info.get("params", {}), term)
        c.items += items
        c.notes += notes
        if kind is not None:
            c.kinds.add(kind)

    # DC paths of the wiring: 1 mH between the ports of one net, to ground on the ground net
    nets = {}
    for n, r in ports.items():
        if r.get("net") is not None:
            nets.setdefault((r["net"], r.get("ground_net", False)), []).append(node[n])
    c.items.append(("comment", "DC paths of the wiring (open at RF)"))
    for (net, ground), members in sorted(nets.items()):
        chain = (["0"] if ground else []) + members
        c.items += [("L", f"Ldc{net}_{i}", a, b, "1m") for i, (a, b) in enumerate(zip(chain, chain[1:]))]
    if not nets:
        c.notes.append("the port map has no nets: no DC paths, the devices get no defined bias (export again)")

    if dc_blocks:
        c.notes.append("no 0 Hz point in the .sNp: the EM model is connected through 1 uF DC blocks")
        c.em_nodes = [f"e{n}" for n in sorted(ports)]
        c.items += [("C", f"Cdc{n}", node[n], f"e{n}", "1u") for n in sorted(ports)]
    else:
        c.em_nodes = [node[n] for n in sorted(ports)]
    return c


def write_spice(c, simulator, em, em_file, em_name, pdk):
    """ngspice or Xyce netlist."""
    out = [f"* {c.name}: EM model with PDK devices for {simulator}, "
           "generated by klayout_em_export tools/spice_wrapper.py",
           "* pins: " + ", ".join(f"{node} = export port {n} (layout port {lp})" for node, n, lp in c.header)]
    if em == "fit":
        out += ["* the EM model's equivalent circuit (snp2le):", f".include {os.path.basename(em_file)}"]
    else:
        out += ["* the EM model: its S-parameters, read by Xyce's YLIN element",
                f".model {c.name}_em LIN TSTONEFILE={em_file}"]
    out.append(f"* PDK model libraries ({simulator}):")
    for kind in sorted(c.kinds):
        lib, section = c.tech.LIBRARIES[kind]
        out.append(("" if pdk else "* ") + f".lib {c.tech.lib_path(pdk, simulator, lib)} {section}")
    out += [f"* notes: {n}" for n in c.notes]
    out += ["", f".subckt {c.name} {' '.join(c.pins)}"]
    if em == "fit":
        out.append(f"XEM {' '.join(c.em_nodes)} {em_name}")
    else:
        out.append(f"YLIN YEM {' '.join(f'{n} 0' for n in c.em_nodes)} {c.name}_em")
    for item in c.items:
        if item[0] == "comment":
            out.append(f"* {item[1]}")
        elif item[0] == "device":
            _, inst, model, nodes, params = item
            out.append(f"{inst} {' '.join(nodes)} {model} " + " ".join(f"{k}={v}" for k, v in params.items()))
        else:
            out.append(f"{item[1]} {item[2]} {item[3]} {item[4]}")
    out += [f".ends {c.name}", ""]
    return "\n".join(out)


def write_spectre(c, em_file):
    """Spectre netlist: the .sNp through an nport element; the PDK includes are left to the user."""
    out = ["simulator lang=spectre",
           f"// {c.name}: EM model with PDK devices for Spectre, generated by klayout_em_export tools/spice_wrapper.py",
           "// pins: " + ", ".join(f"{node} = export port {n} (layout port {lp})" for node, n, lp in c.header),
           f"// {c.tech.SPECTRE_NOTE}"]
    for kind in sorted(c.kinds):
        lib, section = c.tech.LIBRARIES[kind]
        out.append(f'// include "<your PDK>/{lib}" section={section}')
    out += [f"// notes: {n}" for n in c.notes]
    out += ["", f"subckt {c.name} ({' '.join(c.pins)})",
            f"  EM ({' '.join(f'{n} 0' for n in c.em_nodes)}) nport file=\"{em_file}\""]
    names = {"R": ("resistor", "r"), "L": ("inductor", "l"), "C": ("capacitor", "c")}
    for item in c.items:
        if item[0] == "comment":
            out.append(f"  // {item[1]}")
        elif item[0] == "device":
            _, inst, model, nodes, params = item
            out.append(f"  {inst} ({' '.join(nodes)}) {model} " + " ".join(f"{k}={v}" for k, v in params.items()))
        else:
            master, param = names[item[0]]
            out.append(f"  {item[1]} ({item[2]} {item[3]}) {master} {param}={item[4]}")
    out += [f"ends {c.name}", ""]
    return "\n".join(out)


def write_vacask(c, em_file, em_name, primitives):
    """VACASK netlist: snp2le's VACASK model, the PDK's VACASK libraries (by name, through .vacaskrc.toml)."""
    out = [f"// {c.name}: EM model with PDK devices for VACASK, generated by klayout_em_export tools/spice_wrapper.py",
           "// pins: " + ", ".join(f"{node} = export port {n} (layout port {lp})" for node, n, lp in c.header),
           *[f"// {line}" if not line.startswith("include") else line for line in c.tech.VACASK_HEADER]]
    for kind in sorted(c.kinds):
        lib, section = c.tech.LIBRARIES[kind]
        out.append(f'include "{lib}" section={section}')
    out.append("// primitives of the EM model and of this wrapper, under names of their own")
    used = set(primitives) | {"resistor", "inductor", "capacitor"}
    out += [f'load "{p}.osdi"' for p in sorted(used & set(VACASK_MODULES))]   # VACASK's module path
    out += [f"model em_{p} {p}" for p in sorted(used)]
    out += [f"// notes: {n}" for n in c.notes]
    out += [f'include "{os.path.basename(em_file)}"', "", f"subckt {c.name}({' '.join(c.pins)})",
            f"  em ({' '.join(c.em_nodes)}) {em_name}"]
    names = {"R": ("em_resistor", "r"), "L": ("em_inductor", "l"), "C": ("em_capacitor", "c")}
    for item in c.items:
        if item[0] == "comment":
            out.append(f"  // {item[1]}")
        elif item[0] == "device":
            _, inst, model, nodes, params = item
            # the PDK's VACASK subcircuits name their parameters in lower case (nx, ny), and have no 'b'
            values = " ".join(f"{k.lower()}={v}" for k, v in params.items() if k != "b")
            out.append(f"  {inst.lower()} ({' '.join(nodes)}) {model} {values}")
        else:
            master, param = names[item[0]]
            out.append(f"  {item[1].lower()} ({item[2]} {item[3]}) {master} {param}={item[4]}")
    out += ["ends", ""]
    return "\n".join(out)


XSCHEM_HEADER = "v {xschem version=3.4.5 file_version=1.2}\nG {}\n"


def xschem_sides(pins):
    """(left pins, right pins) of the symbol: pins with "out" in their name go to the right; without any such
    pin, the second half does."""
    right = [p for p in pins if "out" in p.lower()]
    if not right or len(right) == len(pins):
        half = (len(pins) + 1) // 2
        return pins[:half], pins[half:]
    return [p for p in pins if p not in right], right


def xschem_symbol(c, netlist_file):
    """xschem symbol of the subcircuit: a box with the pins, in the subcircuit's pin order. spice_sym_def makes
    xschem put an .include of the circuit file (next to the symbol) into the netlist, so placing the symbol in a
    schematic is all it takes."""
    left, right = xschem_sides(c.pins)
    rows = max(len(left), len(right), 1)
    longest = max([len(p) for p in left] or [0]) + max([len(p) for p in right] or [0])
    half = max(80, 10 * (-(-(longest * 7 + 60) // 20)))           # half width of the box, on the 10 grid
    top = -10 * rows - 10
    include = os.path.basename(netlist_file)
    out = [XSCHEM_HEADER + "K {type=subcircuit",
           'format="@name @pinlist @symname"',
           'template="name=x1"',
           f'spice_sym_def="tcleval(.include [file join [file dirname [abs_sym_path @symname\\\\.sym]] {include}])"',
           "}", "V {}", "S {}", "E {}",
           f"L 4 {-half} {top} {half} {top} {{}}", f"L 4 {-half} {-top} {half} {-top} {{}}",
           f"L 4 {-half} {top} {-half} {-top} {{}}", f"L 4 {half} {top} {half} {-top} {{}}"]
    position = {}
    for side, names in ((-1, left), (1, right)):
        for i, pin in enumerate(names):
            position[pin] = (side * (half + 20), top + 20 + 20 * i, side)
    for pin in c.pins:                                              # the pin order of the subcircuit
        x, y, side = position[pin]
        out += [f"L 4 {x} {y} {side * half} {y} {{}}",
                f"B 5 {x - 2.5} {y - 2.5} {x + 2.5} {y + 2.5} {{name={pin} dir=inout}}",
                f"T {{{pin}}} {side * (half - 5)} {y - 4} 0 {1 if side > 0 else 0} 0.2 0.2 {{}}"]
    out += [f"T {{@symname}} {-half} {top - 30} 0 0 0.25 0.25 {{}}",
            f"T {{@name}} {-half} {-top + 5} 0 0 0.2 0.2 {{}}", ""]
    return "\n".join(out), position


def xschem_testbench(c, symbol_file, position, simulator):
    """A starter testbench for xschem: the symbol with a named label at each pin, the PDK's model libraries and an
    operating point analysis. The designer adds sources and loads."""
    name = os.path.basename(symbol_file)
    models = "\n".join(f".lib $::SG13G2_MODELS{'_XYCE' if simulator == 'xyce' else ''}/{c.tech.LIBRARIES[kind][0]} "
                       f"{c.tech.LIBRARIES[kind][1]}" for kind in sorted(c.kinds))
    out = [XSCHEM_HEADER + "K {}", "V {}", "S {}", "E {}",
           "T {The EM model with the PDK devices, from klayout_em_export (Create Circuit)} "
           "-300 -260 0 0 0.4 0.4 {}",
           "T {Add your sources and loads at the pins, and your analysis to the commands below.} "
           "-300 -220 0 0 0.3 0.3 {}",
           f"C {{{name}}} 0 0 0 0 {{name=x1}}"]
    for i, pin in enumerate(c.pins, start=1):
        x, y, side = position[pin]
        out.append(f"C {{devices/lab_pin.sym}} {x} {y} 0 {1 if side > 0 else 0} "
                   f"{{name=p{i} sig_type=std_logic lab={pin}}}")
    out += ["C {devices/code_shown.sym} -300 160 0 0 {name=MODEL only_toplevel=true",
            'format="tcleval( @value )"', 'value="', models, '"}',
            "C {devices/code_shown.sym} 200 160 0 0 {name=" + ("XYCE" if simulator == "xyce" else "NGSPICE")
            + " only_toplevel=true", 'value="',
            ".op" if simulator == "xyce" else ".control\nop\nprint " + " ".join(f"v({pin})" for pin in c.pins) + "\n.endc",
            '"}', ""]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("portmap")
    parser.add_argument("snp", help="the EM result, preferably <model>_dc.sNp (with its 0 Hz point)")
    parser.add_argument("-o", "--output", help="wrapper file (default: <snp name>_<simulator>.<ext> next to the .snp)")
    parser.add_argument("--simulator", choices=sorted(EM_DEFAULT), default="ngspice")
    parser.add_argument("--em", choices=("fit", "snp"), help="EM model: snp2le equivalent circuit or the .sNp file")
    parser.add_argument("--pdk", help="PDK folder (IHP: the ihp-sg13g2 or ihp-sg13cmos5l folder of IHP-Open-PDK): "
                                       "active .lib lines (ngspice, Xyce)")
    parser.add_argument("--no-thermal-noise", dest="thermal_noise", action="store_false",
                        help="--em fit: a noiseless EM model (default: with the EM structure's thermal noise)")
    parser.add_argument("--numbered-pins", action="store_true",
                        help="name the pins port<N>, also where the port map has the net's label from the layout")
    parser.add_argument("--no-xschem", dest="xschem", action="store_false",
                        help="ngspice, Xyce: don't write the xschem symbol and the starter testbench")
    args = parser.parse_args()
    sim = args.simulator
    em = args.em or EM_DEFAULT[sim]
    if em not in EM_ALLOWED[sim]:
        sys.exit(f"{sim} cannot use the EM model as '{em}' (possible: {', '.join(EM_ALLOWED[sim])})")
    out = args.output or os.path.splitext(args.snp)[0] + f"_{sim}" + EXTENSION[sim]
    name = re.sub(r"\W", "_", os.path.splitext(os.path.basename(out))[0])
    portmap = json.load(open(args.portmap))
    dc_blocks = not has_dc_point(args.snp)
    folder = os.path.dirname(os.path.abspath(out))
    em_notes = []
    if em == "fit":
        fmt = "vacask" if sim == "vacask" else "ngspice"
        thermal_noise = args.thermal_noise
        if sim == "xyce":
            if "xyce" in snp2le_formats():
                fmt = "xyce"
            else:
                # the stripped noisy=0 makes the fit resistors noisy: noise is not valid, with or without the generator
                thermal_noise = False
                em_notes.append("snp2le has no Xyce dialect yet (newer than snp2le 0.1.20 on PyPI): the EM model is "
                                "its ngspice model without noisy=0, whose fit resistors add noise that is not the "
                                "structure's: noise results through it are not valid. Install a newer snp2le")
                print(em_notes[-1])
        em_file = os.path.join(folder, name + ("_le.inc" if sim == "vacask" else "_le.cir"))
        em_name, em_pins, notes = equivalent_circuit(args.snp, em_file, fmt, thermal_noise)
        if fmt == "ngspice" and sim == "xyce":
            xyce_compatible(em_file)
        else:
            em_notes += notes
    else:
        em_file, em_name, em_pins = os.path.abspath(args.snp).replace("\\", "/"), None, touchstone_ports(args.snp)
    c = build(portmap, em_pins, dc_blocks, name, args.numbered_pins)
    c.notes += em_notes
    if sim == "vacask":
        text = write_vacask(c, em_file, em_name, vacask_private_models(em_file))
    elif sim == "spectre":
        text = write_spectre(c, em_file)
    else:
        text = write_spice(c, sim, em, em_file, em_name, args.pdk)
    open(out, "w").write(text)
    print("wrote", out, "and", em_file if em == "fit" else f"(uses {em_file})")
    if sim in ("ngspice", "xyce") and args.xschem:
        # for xschem: a symbol named like the subcircuit, and a starter testbench (kept if it is there already:
        # it is the designer's file from then on)
        symbol_file = os.path.join(folder, name + ".sym")
        symbol, position = xschem_symbol(c, out)
        open(symbol_file, "w").write(symbol)
        testbench = os.path.join(folder, name + "_tb.sch")
        kept = os.path.exists(testbench)
        if not kept:
            open(testbench, "w").write(xschem_testbench(c, symbol_file, position, sim))
        print("xschem: wrote the symbol", symbol_file, "and",
              f"kept your testbench {testbench}" if kept else f"the starter testbench {testbench}")


if __name__ == "__main__":
    main()
