# The IHP PDK for the batch tests: a process's KLayout technology and its SG13_dev device library. PDK folder:
# testpaths.PDK_ROOT, which holds ihp-sg13g2 (and ihp-sg13cmos5l for test_cmos5l.py). One process per KLayout run: both
# libraries are called SG13_dev and share the pycell4klayout-api modules.
import importlib
import os
import sys

import pya

from testpaths import PDK_ROOT


def load_pdk(process="sg13g2"):
    """Register the technology and the SG13_dev pcell library of process (sg13g2 or sg13cmos5l), Tcl callbacks
    bypassed. FileNotFoundError without that PDK (run_all reports the test as skipped)."""
    pdk = os.path.join(PDK_ROOT, f"ihp-{process}", "libs.tech", "klayout")
    pydir = os.path.join(pdk, "python")
    lyt = os.path.join(pdk, "tech", f"{process}.lyt")
    if not os.path.isfile(lyt):
        raise FileNotFoundError(f"No such file: {lyt} (run tests/setup_pdk.sh or set IHP_PDK_ROOT)")
    if pydir not in sys.path:
        sys.path.insert(0, pydir)
        sys.path.insert(0, os.path.join(pydir, "pycell4klayout-api", "source", "python"))
    if not pya.Technology.has_technology(process):
        pya.Technology.create_technology(process).load(lyt)
    import cni.dlo
    cni.dlo.PCellWrapper.coerce_parameters = lambda self, layout, v: v
    importlib.import_module(f"{process}_pycell_lib")  # registers SG13_dev for this technology
    return pya.Library.library_by_name("SG13_dev", process)
