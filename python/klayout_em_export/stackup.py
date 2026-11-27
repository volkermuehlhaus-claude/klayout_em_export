"""Read a gds2palace stackup XML: which GDS layers matter for EM, and the metal names.

Plain XML, no gds2palace import: KLayout's Python has no gds2palace. Only the parts the export needs are read.
"""
import xml.etree.ElementTree as ET


class StackupError(Exception):
    pass


def _layer_number(element, path):
    value = element.get("Layer")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise StackupError(f"{path}: Layer=\"{value}\" of {element.get('Name')} is not a plain number "
                           "(expressions in layer numbers are not supported)") from None


def _datatype(element, path, key="Datatype"):
    """The datatype a stackup element names for its layer (stackup format 3.2), or None."""
    value = element.get(key)
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise StackupError(f"{path}: {key}=\"{value}\" of {element.get('Name') or 'an Operand'} is not a plain "
                           "number (expressions in datatypes are not supported)") from None


LAYER_ID_BASE = 10 ** 10        # layer key of a layer with a Datatype: 1 | 5 digits layer | 5 digits datatype,
LAYER_ID_FACTOR = 10 ** 5       # as gds2palace's layer id (68/20 is 10006800020)


def layer_key(number, datatype=None):
    """The key of a stackup layer: its GDS layer number, or, for a layer with a Datatype, a number that holds both
    (68/20 is 10006800020, as gds2palace's layer id). The traced metals, vias, nets and ground marks are keyed by it,
    so two stackup layers on one GDS layer number (a metal on 68/20, its via on 68/44) stay apart."""
    return number if datatype is None else LAYER_ID_BASE + number * LAYER_ID_FACTOR + datatype


def split_key(key):
    """(GDS layer number, datatype or None) of a layer key."""
    key = int(key)
    if key >= LAYER_ID_BASE:
        return (key - LAYER_ID_BASE) // LAYER_ID_FACTOR, key % LAYER_ID_FACTOR
    return key, None


def key_text(key):
    """A layer key as text: "8", or "68/20" with a datatype."""
    number, datatype = split_key(key)
    return str(number) if datatype is None else f"{number}/{datatype}"


def find_layer(layout, key, datatype=0):
    """The layout's layer index of a layer key, or None: the key's own datatype, else datatype (the drawing
    datatype, 0)."""
    number, own = split_key(key)
    return layout.find_layer(number, datatype if own is None else own)


def _number(value):
    """float of a plain number attribute; None for a missing value or a "=expression" (variables)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class StackupLayer:
    def __init__(self, name, kind, layer, material, element=None, path="stackup"):
        self.name = name
        self.kind = kind            # conductor, via, sheet or dielectric
        self.layer = layer          # GDS layer number
        self.material = material
        # the GDS datatype the layer is read from (stackup format 3.2), None: the drawing datatype (0)
        self.datatype = _datatype(element, path) if element is not None else None
        self.key = layer_key(layer, self.datatype)
        get = element.get if element is not None else (lambda key: None)
        self.reference, self.reference_edge = get("Reference"), (get("ReferenceEdge") or "Top").capitalize()
        self.zmin_attr, self.zmax_attr = get("Zmin"), get("Zmax")

    @property
    def is_metal(self):
        return self.kind in ("conductor", "sheet")

    def __repr__(self):
        return f"StackupLayer({self.name!r}, {self.kind!r}, {key_text(self.key)})"


class Stackup:
    def __init__(self, path):
        self.path = path
        root = ET.parse(path).getroot()
        # the layer type in lower case: stackups write conductor, Conductor or CONDUCTOR (gds2palace reads any case)
        self.layers = [StackupLayer(e.get("Name"), (e.get("Type") or "").lower(), _layer_number(e, path),
                                    e.get("Material"), e, path)
                       for e in root.iter("Layer")]
        # dielectric name -> (Reference, ReferenceEdge, Thickness), for the z positions of the layers
        self.dielectrics = {e.get("Name"): (e.get("Reference"), (e.get("ReferenceEdge") or "Top").capitalize(),
                                          e.get("Thickness"))
                            for e in root.iter("Dielectric")}
        # derived layer number -> (name, operation, operand layer numbers)
        self.derived = {_layer_number(e, path): (e.get("Name"), e.get("Operation"),
                                                 [_layer_number(o, path) for o in e.iter("Operand")])
                        for e in root.iter("DerivedLayer")}
        # derived layer number -> (operation, [operand layer keys], Oversize in µm or None if given by a variable):
        # what layers.region needs to compute a derived conductor or via as gds2palace does
        self.derived_spec = {}
        for e in root.iter("DerivedLayer"):
            raw = e.get("Oversize")
            oversize = 0.0 if raw is None or raw.strip() == "" else _number(raw)
            self.derived_spec[_layer_number(e, path)] = (
                (e.get("Operation") or "").upper(),
                [layer_key(_layer_number(o, path), _datatype(o, path)) for o in e.iter("Operand")], oversize)
        # dielectrics with a Boundary= layer: their outline is drawn in the GDS
        self.boundary_layers = sorted({int(e.get("Boundary")) for e in root.iter("Dielectric")
                                       if (e.get("Boundary") or "").lstrip("-").isdigit()})
        # Datatype per layer (stackup format 3.2): {GDS layer number: datatypes the stackup names for it}, from
        # <Layer Datatype>, <Operand Datatype> and <Dielectric BoundaryDatatype>. gds2palace reads such a layer from
        # exactly that datatype. plain: the layer numbers named without one, read from the export's datatypes.
        self.datatypes, self.plain = {}, set()
        named = [(_layer_number(e, path), _datatype(e, path)) for e in root.iter("Layer")]
        named += [(_layer_number(o, path), _datatype(o, path)) for e in root.iter("DerivedLayer")
                  for o in e.iter("Operand")]
        named += [(int(e.get("Boundary")), _datatype(e, path, "BoundaryDatatype")) for e in root.iter("Dielectric")
                  if (e.get("Boundary") or "").lstrip("-").isdigit()]
        for number, datatype in named:
            if number in self.derived:
                continue                    # computed by gds2palace, nothing is read from the layout
            if datatype is None:
                self.plain.add(number)
            else:
                self.datatypes.setdefault(number, set()).add(datatype)
        # <Substrate Offset="..."> (schema 2.0): shifts every Layer that has no Reference. None: given by a variable,
        # then those layers compare only among themselves (z_range anchor "offset")
        offsets = [e.get("Offset") for e in root.iter("Substrate")]
        offset = 0.0 if not offsets else _number(offsets[-1])
        self.offset = offset if offset is None or offset > 0 else 0.0     # as gds2palace: only a positive offset counts

    def layer(self, name):
        return next((l for l in self.layers if l.name == name), None)

    def reads(self, layer, datatype, purposes=(0,)):
        """True if the EM model reads the shapes on this GDS layer and datatype: the datatype the stackup names for
        that layer number, or, for a layer number named without a Datatype, one of the export's datatypes
        (purposes)."""
        return datatype in self.datatypes.get(layer, ()) or (layer in self.plain and datatype in purposes)

    def key_of(self, number, datatype):
        """The key of the stackup layer read from these shapes (GDS layer number and datatype), or None: a layer
        with that Datatype, else a layer of that number without one, on the drawing datatype 0. The checks and
        tools read layers without a Datatype on datatype 0 only."""
        if datatype in self.datatypes.get(number, ()):
            return layer_key(number, datatype)
        if number in self.plain and datatype == 0:
            return number
        return None

    def names(self):
        """{layer key: stackup name}."""
        return {l.key: l.name for l in self.layers}

    def is_traced_derived(self, l):
        """True for a derived conductor or via (e.g. Metal1 computed as 8/0 NOT 8/24) that the checks trace, computed
        from its operands (layers.region). Derived sheets (the SG13G2 resistors) and dielectrics are no wiring, and a
        derived layer with an Oversize given by a variable cannot be computed here."""
        return (l.layer in self.derived and l.kind in ("conductor", "via") and self.derived_spec[l.layer][2] is not None
                and self.derived_spec[l.layer][0] in ("OR", "AND", "NOT", "XOR", "SIZE"))

    def is_traced(self, l):
        """A layer the checks trace or search: drawn directly, or a derived conductor or via (is_traced_derived)."""
        return l.layer not in self.derived or self.is_traced_derived(l)

    def sources(self, number, _seen=()):
        """The drawn layer keys a derived layer is computed from, through derived operands (recursive)."""
        out = set()
        for operand in self.derived_spec.get(number, ((), (), 0))[1]:
            n, own = split_key(operand)
            if own is None and n in self.derived_spec and n not in _seen:
                out |= self.sources(n, _seen + (number,))
            else:
                out.add(operand)
        return out

    def drawn_source(self, key):
        """The drawn layer a layer key stands for in the layout: the key itself, or for a derived layer its first
        operand, through derived operands (Metal1 = 8/0 NOT 8/24: 8/0). The PDK's device cells draw their metal
        there."""
        number, own = split_key(key)
        seen = set()
        while own is None and number in self.derived_spec and number not in seen and self.derived_spec[number][1]:
            seen.add(number)
            key = self.derived_spec[number][1][0]
            number, own = split_key(key)
        return key

    def metal_sources(self, number, _seen=()):
        """The drawn layer keys whose shapes are metal of a derived layer, through derived operands (recursive): all
        operands of OR, the first operand of NOT, AND and SIZE (the others cut or limit it: the slits of Metal1 = 8/0
        NOT 8/24 are on 8/24), none of XOR. The clean-up tools treat these as the derived metal's drawn layers."""
        spec = self.derived_spec.get(number)
        if spec is None or number in _seen or not spec[1]:
            return set()
        operation, operands = spec[0], spec[1]
        if operation == "OR":
            chosen = operands
        elif operation in ("NOT", "AND", "SIZE"):
            chosen = operands[:1]
        else:
            return set()
        out = set()
        for operand in chosen:
            n, own = split_key(operand)
            if own is None and n in self.derived_spec:
                out |= self.metal_sources(n, _seen + (number,))
            else:
                out.add(operand)
        return out

    def derived_metal_sources(self):
        """{drawn layer key: [keys of the derived conductors it is metal of]} (metal_sources of every traced derived
        conductor): the layers Remove Dummy Fill and Fill Density Holes and Merge Metal work on for a derived metal.
        A drawn layer that is also a stackup layer of its own is given under that layer's key (8/0 as 8)."""
        drawn = {}
        for l in self.layers:
            if l.layer not in self.derived:
                drawn[(l.layer, 0 if l.datatype is None else l.datatype)] = l.key
        out = {}
        for l in self.layers:
            if l.kind == "conductor" and self.is_traced_derived(l):
                for key in self.metal_sources(l.layer):
                    n, own = split_key(key)
                    out.setdefault(drawn.get((n, 0 if own is None else own), key), []).append(l.key)
        return out

    def operand_datatypes(self, number):
        """Datatypes of a GDS layer number that operands of derived layers read (an operand without a Datatype reads
        datatype 0)."""
        out = set()
        for spec in self.derived_spec.values():
            for operand in spec[1]:
                n, own = split_key(operand)
                if n == number and not (own is None and n in self.derived_spec):
                    out.add(0 if own is None else own)
        return out

    def derived_keys_of(self, number, datatype):
        """Keys of the traced derived layers (is_traced_derived) computed from these shapes (GDS layer number and
        datatype): a mark on the 8/0 frame counts for Metal1 = 8/0 NOT 8/24. An operand without a Datatype is read
        from datatype 0, as everywhere in the checks."""
        here = {layer_key(number, datatype)} | ({number} if datatype == 0 else set())
        return [l.key for l in self.layers if self.is_traced_derived(l) and self.sources(l.layer) & here]

    def metal_names(self):
        """Conductor and sheet layers, top to bottom as in the file: the choices for port layers."""
        return [l.name for l in self.layers if l.is_metal]

    def _edge(self, name, edge, seen=()):
        """z of the Top or Bottom edge of a layer or dielectric, as (anchor, offset), or None if unknown.
        A thickness given by a variable starts a new anchor, so z values compare only within one anchor; the
        metal stack hangs off one anchor (e.g. the bottom of SiO2) and needs no variable."""
        if name in seen:
            raise StackupError(f"{self.path}: Reference loop at {name}")
        layer = self.layer(name)
        if layer is not None:
            z = self.z_range(layer, seen + (name,))
            return None if z is None else (z[0], z[2] if edge == "Top" else z[1])
        if name in self.dielectrics:
            reference, reference_edge, thickness = self.dielectrics[name]
            bottom = ("bottom", 0.0) if not reference else self._edge(reference, reference_edge, seen + (name,))
            if edge == "Bottom" or bottom is None:
                return bottom
            t = _number(thickness)
            return (bottom[0], bottom[1] + t) if t is not None else (f"{name}.top", 0.0)
        return None

    def z_range(self, layer, seen=()):
        """(anchor, zmin, zmax) of a stackup layer, or None if its position cannot be resolved.
        With a Reference, Zmin/Zmax are offsets from that edge; without, they are absolute, plus the stackup's
        <Substrate Offset>."""
        zmin, zmax = _number(layer.zmin_attr), _number(layer.zmax_attr)
        if zmin is None or zmax is None:
            return None
        if not layer.reference:
            # an offset given by a variable shifts all these layers alike: an anchor of their own, like a thickness
            return ("offset", zmin, zmax) if self.offset is None else ("bottom", zmin + self.offset, zmax + self.offset)
        base = self._edge(layer.reference, layer.reference_edge, seen)
        return None if base is None else (base[0], base[1] + zmin, base[1] + zmax)

    def unresolved(self):
        """Names of the metals and vias drawn in the GDS whose z position cannot be resolved (a position given by
        a variable or expression, or an unknown Reference). Such a layer is left out of everything that needs
        heights: via connections, ground and nets, port direction. Dielectric layers (e.g. LBE) do not count."""
        return [l.name for l in self.layers
                if l.kind in ("conductor", "sheet", "via") and l.layer not in self.derived and self.z_range(l) is None]

    def is_above(self, upper, lower):
        """True if the layer named upper lies above the layer named lower (by their bottom), False if below, None
        if their positions cannot be compared."""
        a, b = self.layer(upper), self.layer(lower)
        za, zb = (self.z_range(a) if a else None), (self.z_range(b) if b else None)
        if za is None or zb is None or za[0] != zb[0]:
            return None
        return za[1] > zb[1]

    def via_neighbors(self, delta=1e-5):
        """{via layer key: ([metals directly below], [metals directly above])} as StackupLayers, for the vias
        drawn in the GDS (or derived ones the checks compute) that have such metals on both sides (z within delta, as gds2palace). Lists, because
        a via can sit on more than one layer (Cont: on Activ and on the REF_FOR_TRANSISTOR sheet)."""
        # drawn metals and the derived conductors the checks compute (is_traced_derived); not derived sheets
        metals = [(l, self.z_range(l)) for l in self.layers if l.is_metal and self.is_traced(l)]
        out = {}                    # keyed by the via's layer key
        for via in (l for l in self.layers if l.kind == "via" and self.is_traced(l)):
            z = self.z_range(via)
            if z is None:
                continue
            below = [m for m, mz in metals if mz and mz[0] == z[0] and abs(mz[2] - z[1]) < delta]
            above = [m for m, mz in metals if mz and mz[0] == z[0] and abs(mz[1] - z[2]) < delta]
            if below and above:
                out[via.key] = (below, above)
        return out

    def gds_layers(self):
        """GDS layer numbers the EM model reads: stackup layers and dielectric boundaries, with derived layers
        replaced by their (recursive) source layers, since derived layers are computed by gds2palace."""
        needed = set()

        def add(number, seen=()):
            if number in self.derived:
                if number in seen:
                    raise StackupError(f"{self.path}: derived layer {number} refers to itself")
                for operand in self.derived[number][2]:
                    add(operand, seen + (number,))
            else:
                needed.add(number)

        for l in self.layers:
            add(l.layer)
        for number in self.boundary_layers:
            add(number)
        return sorted(needed)
