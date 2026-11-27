"""The shapes of a stackup layer in a cell, as the EM model sees them: a drawn layer from its datatype, a derived layer
(stackup <DerivedLayers>, e.g. Metal1 computed as 8/0 NOT 8/24 to cut slits) from its operands, with gds2palace's
boolean operations. Used by the ground check, the nets, the EM Port tool and the ground marks; the export writes the
operands and leaves the computing to gds2palace.

gds2palace folds the operands pairwise, (op1 <operation> op2) <operation> op3 ..., and then grows (positive) or
shrinks (negative) the result by Oversize. Here the same with KLayout regions; the corners of a sized region are
KLayout's (gds2palace: mitred), which does not matter for connectivity.
"""
import pya

from .stackup import find_layer, split_key

OPERATIONS = ("OR", "AND", "NOT", "XOR", "SIZE")


def _drawn(layout, cell, key, box, datatype):
    li = find_layer(layout, key, datatype)
    if li is None:
        return pya.Region()
    return pya.Region(cell.begin_shapes_rec(li) if box is None else cell.begin_shapes_rec_touching(li, box))


def region(layout, cell, stackup, key, box=None, datatype=0, clip=True, _seen=()):
    """Merged Region of a stackup layer key in cell (through the hierarchy), clipped to box (Box in dbu) if given.
    A derived layer is computed from its operands; None if it cannot be (an Oversize given by a variable, an
    operation this module does not know, a derived layer that uses itself). A drawn layer is read from its own
    Datatype, else from datatype. clip False: the shapes touching box, whole (the EM Port tool looks for their
    edges; a clip would add edges along the box)."""
    number, own = split_key(key)
    spec = stackup.derived_spec.get(number) if (stackup is not None and own is None) else None
    if spec is None:
        result = _drawn(layout, cell, key, box, datatype)
    else:
        operation, operands, oversize = spec
        if number in _seen or oversize is None or operation not in OPERATIONS or not operands:
            return None
        grow = round(abs(oversize) / layout.dbu) + 1 if oversize else 0
        wide = None if box is None else box.enlarged(grow, grow)     # what an Oversize can move into the box
        parts = []
        for operand in operands:
            part = region(layout, cell, stackup, operand, wide, datatype, clip, _seen + (number,))
            if part is None:
                return None
            parts.append(part)
        result = parts[0]
        for part in parts[1:]:
            if operation == "OR":
                result = result + part
            elif operation == "AND":
                result = result & part
            elif operation == "NOT":
                result = result - part
            elif operation == "XOR":
                result = result ^ part
        if oversize:
            result = result.sized(round(oversize / layout.dbu))
    if box is not None and clip:
        result = result & pya.Region(box)
    return result.merged()


def polygon_at(layout, cell, stackup, key, point):
    """The polygon of a stackup layer that contains point (Point in dbu), in cell coordinates, or None. A derived
    layer is computed over the whole cell for this (a click: once)."""
    if split_key(key)[1] is None and key in stackup.derived_spec:
        shapes = region(layout, cell, stackup, key)
        if shapes is None:
            return None
        for polygon in shapes.each():
            if polygon.inside(point):
                return polygon.dup()
        return None
    li = find_layer(layout, key)
    if li is None:
        return None
    it = cell.begin_shapes_rec_touching(li, pya.Box(point, point))
    while not it.at_end():
        shape = it.shape()
        if not shape.is_text() and shape.polygon is not None:
            polygon = shape.polygon.transformed(it.trans())
            if polygon.inside(point):
                return polygon
        it.next()
    return None
