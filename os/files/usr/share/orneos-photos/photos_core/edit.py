"""An edit as the window makes it (quarter turns, mirror, a crop drawn on the turned photo, light, contrast,
saturation, warmth, black and white or sepia) turned into what Memories applies on the server (the state of
the Filerobot editor its web page uses).

The server first turns the photo upright from its EXIF, then crops (in that frame), mirrors, turns, and only
then adjusts the colours: the crop drawn on the turned photo is brought back into the upright frame here.
"""
KEEP = ("jpg", "jpeg", "png", "webp")


def _back(x, y, rotate, flip_h, flip_v):
    """A point of the shown photo (0..1) back in the upright original."""
    r = rotate % 360
    if r == 90:
        u, v = y, 1 - x
    elif r == 180:
        u, v = 1 - x, 1 - y
    elif r == 270:
        u, v = 1 - y, x
    else:
        u, v = x, y
    if flip_h:
        u = 1 - u
    if flip_v:
        v = 1 - v
    return u, v


def crop_in_original(crop, rotate, flip_h, flip_v):
    x, y, w, h = (float(crop.get(k, d)) for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1)))
    corners = [_back(cx, cy, rotate, flip_h, flip_v) for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))]
    us, vs = [c[0] for c in corners], [c[1] for c in corners]
    left, top = max(0.0, min(us)), max(0.0, min(vs))
    return {"x": round(left, 5), "y": round(top, 5),
            "width": round(min(1.0, max(us)) - left, 5), "height": round(min(1.0, max(vs)) - top, 5)}


def is_identity(edit):
    crop = edit.get("crop") or {}
    return int(edit.get("rotate") or 0) % 360 == 0 and not edit.get("flipH") \
        and not edit.get("flipV") and not edit.get("filter") \
        and all(abs(float(edit.get(k) or 0)) < 1e-3 for k in ("brightness", "contrast", "saturation", "warmth")) \
        and all(abs(float(crop.get(k, d)) - d) < 1e-3 for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1)))


def state(edit):
    """The server's edit state from the window's: {rotate, flipH, flipV, crop {x,y,w,h}, brightness, contrast,
    saturation (-1..1), warmth (0..1), filter ("" | "bw" | "sepia")}."""
    rotate = int(edit.get("rotate") or 0) % 360
    flip_h, flip_v = bool(edit.get("flipH")), bool(edit.get("flipV"))
    out = {"adjustments": {"rotation": rotate, "isFlippedX": flip_h, "isFlippedY": flip_v}}
    crop = edit.get("crop") or {}
    if any(abs(float(crop.get(k, d)) - d) > 1e-3 for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1))):
        out["adjustments"]["crop"] = crop_in_original(crop, rotate, flip_h, flip_v)
    tunes, props = [], {}
    b, c = float(edit.get("brightness") or 0), float(edit.get("contrast") or 0)
    s, w = float(edit.get("saturation") or 0), float(edit.get("warmth") or 0)
    if abs(b) > 1e-3:
        tunes.append("Brighten")
        props["brightness"] = round(b * 0.3, 4)
    if abs(c) > 1e-3:
        tunes.append("Contrast")
        props["contrast"] = round(c * 40, 2)
    if abs(s) > 1e-3:
        tunes.append("HSV")
        props.update(hue=0, saturation=round(s * 1.5, 3), value=0)
    if w > 1e-3:
        tunes.append("Warmth")
        props["warmth"] = round(w * 40, 2)
    if tunes:
        out["finetunes"] = tunes
        out["finetunesProps"] = props
    flt = {"bw": "BlackAndWhite", "sepia": "Sepia"}.get(str(edit.get("filter") or ""))
    if flt:
        out["filter"] = flt
    return out


def target(basename, copy, suffix):
    """(name, extension) the edit is saved under: over the photo, or as « Nom (modifiée).jpg ». Formats the
    server cannot write back (HEIC, TIFF…) always give a JPEG copy."""
    stem, dot, ext = basename.rpartition(".")
    if not dot:
        stem, ext = basename, ""
    ext = ext.lower()
    if ext not in KEEP:
        return f"{stem} {suffix}.jpg", "jpeg"
    if copy:
        return f"{stem} {suffix}.{basename.rpartition('.')[2]}", "jpeg" if ext == "jpg" else ext
    return basename, "jpeg" if ext == "jpg" else ext
