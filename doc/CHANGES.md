# What's new

## Highlights

- Stackups with a datatype per layer, and metals computed from other layers (0.5.0)
- Create Circuit writes an xschem symbol and testbench; pins named after your nets (0.5.0)
- MOS capacitors and the varactor replaced by ports (0.5.0)
- Faster with large layouts; EM off when the panel is closed (0.4.0)
- Split a large region into pieces; port walls (0.3.0)
- Thermal export (0.3.0)

## 0.5.0 (24 November 2026)

Needs gds2palace 0.13.0 or newer.

### New

**Datatype per stackup layer.**  
A stackup can name the datatype of a layer, e.g. a metal on 68/20 and its via on 68/44. The export, checks, ports,
ground marks and clean-up tools read each layer from its datatype. IHP stackups work as before.
[Reference](REFERENCE.md)

**Metals computed from other layers.**  
A stackup can compute a metal, e.g. Metal1 as 8/0 NOT 8/24 to cut slits. The checks now trace such a metal: a click
on the 8/0 frame marks Metal1 as ground, and the slits separate the pieces. Remove Dummy Fill and Merge Metal work on
8/0 and never touch the slits. [Ground checks](userguide/klayout_em_export_userguide.md#checks-ground-and-short-circuits),
[dummy fill](userguide/klayout_em_export_userguide.md#dummy-metal-fill)

**xschem symbol and testbench.**  
For ngspice and Xyce, Create Circuit also writes an xschem symbol and a starter testbench with the PDK models.
`examples/cascode/xschem` has a finished one. [Using it in xschem](userguide/klayout_em_export_userguide.md#using-it-in-xschem)

**Pins named after your nets.**  
Circuit pins take the names of the text labels on the metals (`Cas_in`, `Cas_out`), else `port<N>` as before. The
pin order is unchanged. Export again to get the names.

**MOS capacitors and the varactor replaced by ports.**  
moscap_n, moscap_p and SVaricap are replaced like transistors; Create Circuit adds their PDK models.
[Transistors and resistors](userguide/klayout_em_export_userguide.md#transistors-and-resistors), [limits](userguide/klayout_em_export_userguide.md#limits)

**SG13CMOS5L with IHP's own PDK.**  
Tested with IHP-Open-PDK's `ihp-sg13cmos5l` and its `SG13_dev` library.

### Changed behaviour

- Thermal: the polysilicon heads of resistors now carry heat to the contacts (on `HEAT_RESISTOR`). Lower thermal
  resistance, e.g. about 40 % for a 0.5 × 0.5 µm rhigh. [Heat sources](userguide/klayout_em_export_userguide.md#heat-sources)

### Fixes

- Thermal export with a stackup without the devices' heat source layer (e.g. an interposer) was refused even
  without devices.
- rf MOSFETs from IHP's current PDK were refused ("pin ... has no name").

## 0.4.0 (16 November 2026)

Needs setupEM 0.18.4 or newer for Ctrl+S after Open in setupEM.

### New

**Faster with large layouts.**  
Closing the EM panel switches EM off, and a layout opened for other work is not checked until you start an EM
setup. The checks themselves are faster, e.g. 3.5 s instead of 12.9 s on a 10 MB PA layout with fill.

**Create Circuit: the EM model carries its thermal noise.**  
A noise figure through the circuit now includes the loss of the EM structure. Needs an snp2le that can add it;
otherwise the netlist header says so. [Create Circuit](userguide/klayout_em_export_userguide.md#back-to-the-circuit-create-circuit)

**Create Circuit for Xyce: valid noise results.**  
Uses snp2le's Xyce format, so the fit's resistors are noiseless in Xyce as in ngspice. With an older snp2le the
netlist header says that noise results are not valid.

### Fixes

- An exported EM model opened in KLayout advised Undo Replace, which would have deleted its device ports.
- Relative paths in a `.simcfg` or `.tsimcfg` were read relative to KLayout's start folder, not to the file.

## 0.3.2 (13 November 2026)

### Changed behaviour

- A short circuit at a via port and ground at a region cut are judged near the port (within 10 µm). A winding
  grounded at its far end is now a signal at the cut and gets a proposed port.

### Fixes

- A port wall without in-plane ports stayed in the export, and gds2palace stopped ("port wall ... has no port").

## 0.3.1 (11 November 2026)

Split regions with port walls need gds2palace 0.10.1 and setupEM 0.18.1 or newer.

### Fixes

- Stackups with `Type="Conductor"` (another case, e.g. PCB stackups) found no metals and the panel failed.

## 0.3.0 (10 November 2026)

First version in KLayout's package manager (Tools > Manage Packages). Needs gds2palace 0.10.0 and setupEM 0.18.

### New

**Split a large region into pieces.**  
Several region boxes that share edges are simulated as separate models and joined in setupEM; after a change, only
the changed pieces run again. [Splitting the region](userguide/klayout_em_export_userguide.md#splitting-the-region-into-pieces)

**Port walls.**  
Create Proposed Ports with "as port walls" puts calibrated in-plane ports where lines cross the region edge.
[Port walls](userguide/klayout_em_export_userguide.md#port-walls-calibrated-ports-at-the-cut)

**Thermal export (experimental).**  
Transistors and resistors as heat sources for setupThermal, with instance names from LVS.
[Thermal simulation](userguide/klayout_em_export_userguide.md#thermal-simulation)

**Draw Region and Ground tools.**  
Drag a rectangle as the region box (Shift+drag adds a piece); click a metal to mark it as ground.

**Devices and ports tables.**  
Replace or put back only the selected devices; renumber ports from the right-click menu. Only devices inside the
region box are listed.

**Examples and FAQ.**  
`examples/` has the cascode of the user's guide and a split region with port walls.

### Changed behaviour

- The EM menu is ordered by workflow step; the EM tool icons show only while the EM panel is open.
- Create Circuit presets the PDK folder, the EM result and the Python with snp2le.

### Removed

- Opening an export in EMStudio; the Linux edition of the user's guide.
