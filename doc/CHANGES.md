# What's new

## 0.5.0 (24 November 2026)

**Create Circuit: symbol and testbench for xschem.** For ngspice and Xyce, Create Circuit now also writes an
xschem symbol of the circuit and a starter testbench with the PDK's model library. Open the testbench in xschem,
add sources and loads, and simulate: the symbol brings the circuit file along. `examples/cascode/xschem` has a
finished testbench of the cascode with bias tees, S-parameter analysis and result graphs (user's guide, chapter
"Back to the circuit").

**Create Circuit: pins named after your nets.** The circuit's pins now have the names of their nets in the layout,
e.g. `Cas_in`, `Cas_out` and `Cas_Bias` for the cascode, instead of `port1`, `port2` and `port15`. The export reads
the text labels on the metals (SG13G2: a metal's text or pin layer) and writes them into the port map. A pin whose
net has no label is still `port<N>`. The order of the pins is the same as before, so existing testbenches keep
working. Export again to get the names: a port map of an earlier export has none.

Works with gds2palace 0.13.0 or newer for the resistor heads below; an older gds2palace stops on them with "Cont
touches another conductor layer". Without `HEAT_RESISTOR` in the stackup, nothing changes.

**Thermal: resistor heads carry heat to the contacts.** The heat source of a resistor is its polysilicon body; the
polysilicon heads under the contacts are not heated, but they conduct heat from the body into the contacts and
Metal1. Before, they were missing, and the body reached its contacts only through oxide. The thermal export now
draws them on `HEAT_RESISTOR` as plain shapes, without the contacts' footprints, and the thermal map lists their area
(`unheated_poly_um2`). For a 0.5 × 0.5 µm rhigh this lowers the thermal resistance by about 40 %, for 4 × 4 µm by
about 8 %.

**Fix: thermal export with a stackup without the devices' heat source layer** (e.g. an interposer stackup without
Activ). The Thermal mode refused it ("no layer for the heat sources"), even for a region without devices, so the
layout could not be exported at all. That layer is now only needed when the region has devices: without devices,
Sources says "no devices in the region" as usual, and the export writes the model, with your own heat source markers.
A region with devices and no such layer is still refused, and the message says how many devices need it.

**MOS capacitors and the varactor are replaced by ports.** moscap_n (G, SUB), moscap_p (G, NW) and the HV varactor
SVaricap (G1, W, G2) are recognized and replaced like transistors, one port per terminal; Create Circuit puts in
their PDK models (sg13_moscap_n/p from cornerMOSCAP.lib, sg13_hv_svaricap from cornerMOShv.lib, its substrate node
to ground). Their capacitance is in the gate oxide, which the EM model does not have. Their pins are named only by a
property in IHP's newer PDK versions; without it, the pins over the gate poly are the gates. No heat source in a
thermal export. In Create Circuit, ngspice runs both models; VACASK and Xyce only partly (the PDK's models for them,
see Limits in the user's guide). A static cell of them (no pcell context) is found but not replaced: no size.

**Fix: rf MOSFETs with IHP's current PDK.** IHP-Open-PDK since October 2026 (main and dev, until IHP takes in
the fix in its pycell4klayout-api of 19 November 2026) draws stray copies of the rf MOSFETs' pins, off the device,
named only by a property. The device was refused ("pin ... has no name") and not replaced. Such copies no longer
count as pins.

**SG13CMOS5L with IHP's own PDK.** IHP-Open-PDK now has `ihp-sg13cmos5l`, with its own `SG13_dev` library for the
KLayout technology `sg13cmos5l`. The plug-in is tested with it (`tests/test_cmos5l.py`): the same devices, terminals,
ports and thermal export as with SG13G2. The tests' PDK checkout (`tests/setup_pdk.sh`) now has both processes, at
IHP-Open-PDK main of 10 November 2026.

## 0.4.0 (16 November 2026)

Works with setupEM 0.18.4 or newer for one more thing: after Open in setupEM, Ctrl+S in setupEM saves into the
export's `.simcfg` (before, Ctrl+S did nothing there, and changes were lost unless saved with Save Config).

**Faster with large layouts:** after a layout was opened, the EM panel's checks could take much longer than reading
the file (a 10 MB PA layout with fill: 0.1 s to read, 9 to 13 s of checks), and they ran for every layout opened
after an EM export, because the last stackup used applies to every layout. Now:

- **Closing the EM panel switches EM off**: no checks at all, and the panel stays closed at the next KLayout start
  until EM > EM Panel opens it.
- **A layout opened for other work is not checked**: no region box, no ports in its cell, no ground marks, and its
  stackup only the last one used. Ground and Devices say "not checked: no EM setup in this layout yet"; choosing the
  stackup, drawing a region or port, or Run Checks start the checks.
- **The checks themselves are faster**, with the same results: each cell is identified as a device once, not each
  of its instances (681,000 instances of 74 cells in the PA layout); the scan for the tags of replaced devices reads
  only shapes with properties; tracing a device terminal copies the metal of a layer only when it gets there. The
  PA layout: 3.5 s instead of 12.9 s, a 14 MB layout with fill 2.2 s instead of 5.0 s, a 65 MB RF front end
  15 s instead of 20 s (most of it the ground tracing of the large region).

**Fix: an exported EM model opened in KLayout.** The export removes the replaced devices and keeps their ports, with
the tags that name the device. Opened in KLayout, such a file showed "ports of N device(s) no longer there" and
advised Undo Replace, which would have deleted the device ports from the model. A layout that is the GDS file of its
own `.simcfg` and has device ports but none of their devices is now recognised as an exported model: the Devices step
says "exported EM model: N device(s) replaced by M port(s)", and Replace All and Undo Replace are off.

**Fix:** relative paths in a `.simcfg` or `.tsimcfg` (GdsFile, SubstrateFile; the export writes them relative) are
now read relative to that file, as setupEM reads them. Before, they were relative to KLayout's working directory, so
the layout's own setup file and its stackup were only found when KLayout was started in that folder.

**Create Circuit: the EM model carries its thermal noise.** The snp2le equivalent circuit was noiseless, so a noise
figure through it missed the loss of the EM structure (cascode, ngspice: 1.74 dB instead of 1.81 dB at 10 GHz). The
wrapper now asks snp2le for the structure's thermal noise (`--thermal-noise`); if snp2le cannot add it (the fit not
strictly passive), the model is made without it and the netlist header says so. `tools/spice_wrapper.py
--no-thermal-noise` leaves it out on purpose.

**Create Circuit for Xyce: snp2le's Xyce format.** For Xyce the wrapper took snp2le's ngspice model and removed
`noisy=0`, which Xyce does not know. That made the fit's resistors noisy: a noise analysis in Xyce gave nonsense
(cascode: a noise figure of 112 dB at 10 GHz). snp2le's new Xyce format writes them as noiseless conductances (cascode:
1.59 dB, with the thermal noise). The wrapper uses it when the installed snp2le offers it; the format is newer than
snp2le 0.1.20 on PyPI, so it is checked through `snp2le convert --help`, not by version. With an older snp2le the
netlist header says that noise results are not valid. Bias and S21 are unchanged in ngspice, Xyce and VACASK
(`tests/simulators`).

**Documentation:** gds2palace 0.10.7 changed the frequencies that replace DC in a sweep from 0 Hz: still 10 MHz and
20 MHz for most models, higher for a mesh finer than 0.5 µm (5 MHz·µm divided by the smallest cell size). The user's
guide, `REFERENCE.md`, `ARCHITECTURE.md` and the description at the top of `tools/spice_wrapper.py` said 10 MHz and
20 MHz as a fixed fact and now say "normally". The cascode test report notes that gds2palace 0.10.7 no longer resamples the `_dc`
file.

## 0.3.2 (13 November 2026)

**Fix:** a short circuit at a via port, and ground at a cut of the EM region box, are now judged near the port
(within 10 µm, or the port's own length if that is longer). Before, any connection through the layout counted: a
balun or inductor winding grounded at its other end was "ground" at the cut and got no proposed port, and a port
drawn on it was reported as a short circuit. At RF the winding is an inductance; such a cut now gets a proposed port
("signal (grounded only away from the cut)"), a port on it is not reported, and its signal end (port map, direction)
is the winding, not the ground plane.

**Fix:** a side of the region that was a port wall in the `.simcfg` but has no in-plane port any more (the ports
were changed to via ports) stayed a port wall after the export, and gds2palace stopped with "port wall ... has no
port". The export now takes the port wall off: the side gets the boundary, dielectric margin and air of the other
sides again, and its port wall extension and reference plane shift are removed.

Related fixes outside the plug-in: port walls with the conformal passivation stackup
(`SG13G2_FEM_200um_passi3D.xml`) need gds2palace 0.10.5 (the passivation reached past the cut and moved the wall
away from the ports); a model script opened on another machine (Windows and Linux in turn) keeps the paths
setupEM shows, from setupEM 0.18.2.

## 0.3.1 (11 November 2026)

Split regions with port walls need gds2palace 0.10.1 and setupEM 0.18.1 or newer (both on PyPI): with older
versions, a side of the region made a port wall in setupEM after the export was a plain PEC wall in every piece
and in the full model, and a wide cut across many lines got long standards and a low frequency limit.

**Fix:** stackups that write the layer type in another case, e.g. `Type="Conductor"` in a PCB stackup, now work:
the plug-in read only `conductor`, found no metals, and the panel failed on every refresh with
"min() iterable argument is empty" (the Devices and Ports lines showed "no layout loaded"). The layer type and
`ReferenceEdge` are now read in any case, as gds2palace does. A stackup without any conductor lists no devices
instead of failing.

## 0.3.0 (10 November 2026)

First version in KLayout's package manager (Tools > Manage Packages).

**Split a large region into pieces.** Several EM region boxes on 800/0 that share edges form one region in pieces.
Each piece is simulated as its own model, and setupEM joins the results into one result of the whole region; after
a change, only the changed pieces are simulated again. **Split Region** cuts a box at a click, **Import Pieces...**
takes the boxes and ground marks from an earlier export. Needs gds2palace 0.10.0 and setupEM 0.18.

**Port walls.** **Create Proposed Ports** with **as port walls** puts in-plane ports where lines cross the region
edge; gds2palace calibrates them with the reference plane on the wall. The ports at a cut between pieces are always
port walls.

**Draw Region tool:** drag a rectangle as the EM region box; Shift+drag adds a piece.

**Ground tool:** a click on a metal marks it as ground, through the cell hierarchy, every part of it inside the box.

**Devices:** only the devices in the EM region box are listed and replaced. The device table's right-click menu
replaces or puts back the selected devices only, e.g. to leave a device off the EM signal path as drawn. Static
MOSFETs (drawn without a pcell) get their size from the drawn gates.

**Ports:** the ports table's right-click menu moves a port up or down in the numbering or gives it another number.

**EM menu by workflow step** (Clean Up Layout, Region, Ground, Ports, Thermal). The EM tool icons are in the toolbar
only while the EM panel is open.

**Create Circuit** presets the PDK folder, the EM result (the calibrated one with port walls, the joined one for a
split region) and the Python with snp2le.

**Thermal export (experimental)** for setupThermal: transistors and resistors as heat sources, with schematic
instance names from an LVS database; the panel switches between **EM** and **Thermal**. The export keeps the
layout's datatypes, not only 0.

**Examples:** `examples/` has the user's guide's cascode, with its EM result to try Create Circuit, and a split
region with port walls and reference results. New: an FAQ for designers.

**Removed:** opening an export in EMStudio, until EMStudio has the `.simcfg` import; the Linux edition of the user's
guide.
