#!/usr/bin/env python3
"""
Convert the downloaded BodyParts3D STL files into the compact `.temesh` format the
app loads at runtime.

Why a custom format: the raw STLs are ~32 MB of unindexed triangle soup (the heart wall
alone is 331k triangles with every vertex repeated three times). Runtime STL parsing is
slow, the app bundle would be huge, and the slicer wants flat contiguous arrays anyway.
This welds duplicate vertices, optionally decimates, recentres the model on the heart,
and writes indexed float32/uint32 buffers that Swift can read with a straight memcpy.

Coordinate frame (verified by inspecting the geometry, see ASSETS.md):
BodyParts3D is a whole-body model in millimetres, +X = patient left, +Y = posterior,
+Z = superior (an LPS/DICOM-style frame). Output keeps those axes but translates the
origin to the centroid of the heart wall, so the app works in heart-local millimetres.

Usage:  python3 scripts/build_meshes.py
"""
import struct, os, glob, json, math

SRC = "Assets/BodyParts3D"
OUT = "Assets/HeartMeshes"
WELD_MM = 0.35        # vertices closer than this collapse together
# Peripheral lung vasculature is in the source data but is not mediastinal anatomy: the
# pulmonary trees run to x = +/-124 mm, out into both lungs, where they bury the heart in
# the 3D view and litter the echo image with vessel cross-sections. Clip them back to the
# hilum. Values are heart-centred millimetres.
# The posterior (+y) bound matters anatomically, not just cosmetically. The transducer
# sits in the esophagus at y = +62 mm (see ProbeGeometry.Anatomy), and the pulmonary
# arteries and veins are *anterior* to the esophagus in the mediastinum - they are never
# behind it. Left at +95 the cropped trees sprawled past the probe, so the beam originated
# inside vessels it should have been looking at from behind.
CROP_BOX = {
    "FMA66326": ((-70, 70), (-95, 58), (-120, 120)),   # pulmonary artery
    "FMA66643": ((-70, 70), (-95, 58), (-120, 120)),   # pulmonary veins
}
DEFAULT_CROP = ((-110, 110), (-110, 110), (-160, 150))

CLUSTER_MM = {        # per-structure decimation grid; None = weld only
    "FMA7274": 0.9,   # wall of heart - the big one, 331k tris
    "FMA66326": 1.4,  # pulmonary artery
    "FMA66643": 1.4,  # pulmonary vein
    "FMA7234": 0.8,   # tricuspid valve
    "FMA3784": 0.9,   # descending aorta
}

# Layers whose cross-section the app fills as solid tissue. Only these need to be
# watertight, and only these are worth capping: a cap is an artificial flat face, and
# slicing one edge-on draws a straight line across the image that is not anatomy. The
# great vessels are outlined rather than filled (they are single-surface tubes, so their
# interior is lumen, not tissue), so leaving them open costs nothing and avoids the
# artifact. See AnatomicalLayer.fillsAsSolidTissue in HeartModel.swift.
FILLED_LAYERS = {"myocardium", "valves", "chambers"}

# id -> (display name, layer, render hint)
STRUCTURES = {
    "FMA7274":  ("Wall of Heart",        "myocardium",   True),
    "FMA7235":  ("Mitral Valve",         "valves",       True),
    "FMA7234":  ("Tricuspid Valve",      "valves",       True),
    "FMA7246":  ("Pulmonary Valve",      "valves",       True),
    "FMA3736":  ("Ascending Aorta",      "greatVessels", True),
    "FMA3768":  ("Aortic Arch",          "greatVessels", True),
    "FMA3784":  ("Descending Aorta",     "greatVessels", True),
    "FMA4720":  ("Superior Vena Cava",   "greatVessels", True),
    "FMA10951": ("Inferior Vena Cava",   "greatVessels", True),
    "FMA66326": ("Pulmonary Artery",     "greatVessels", True),
    "FMA66643": ("Pulmonary Veins",      "greatVessels", True),
    "FMA4706":  ("Coronary Sinus",       "greatVessels", True),
    "FMA7260":  ("RV Anterior Papillary", "chambers",    True),
    "FMA7261":  ("RV Posterior Papillary","chambers",    True),
    "FMA7262":  ("RV Septal Papillary",   "chambers",    True),
    "FMA7266":  ("LV Posterior Papillary","chambers",    True),
    "FMA9352nsn":("LV Papillary Muscle",  "chambers",    True),
}


def load_stl(path):
    with open(path, "rb") as f:
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
        data = f.read(n * 50)
    tris = []
    for i in range(n):
        v = struct.unpack_from("<9f", data, i * 50 + 12)
        tris.append((v[0:3], v[3:6], v[6:9]))
    return tris


def build_indexed(tris, grid):
    """Weld/cluster vertices onto a grid and emit an indexed mesh."""
    inv = 1.0 / grid
    lookup = {}
    verts = []
    idx = []
    for tri in tris:
        ids = []
        for p in tri:
            key = (round(p[0] * inv), round(p[1] * inv), round(p[2] * inv))
            j = lookup.get(key)
            if j is None:
                j = len(verts)
                lookup[key] = j
                verts.append(p)
            ids.append(j)
        # drop triangles that collapsed to a line or point during clustering
        if ids[0] != ids[1] and ids[1] != ids[2] and ids[0] != ids[2]:
            idx.extend(ids)
    return verts, idx


def count_open_edges(idx):
    """Edges belonging to exactly one triangle. Zero means the surface is closed."""
    from collections import defaultdict
    use = defaultdict(int)
    for t in range(0, len(idx), 3):
        a, b, c = idx[t], idx[t + 1], idx[t + 2]
        for u, v in ((a, b), (b, c), (c, a)):
            use[(min(u, v), max(u, v))] += 1
    return sum(1 for n in use.values() if n == 1)


def cap_holes(verts, idx):
    """Close open boundaries so the mesh is watertight again.

    Cropping deletes triangles, which leaves the cut end of a vessel open, and welding
    can punch small holes wherever the source data was already non-manifold. That matters
    more than it sounds: the echo renderer decides which pixels are inside tissue by
    counting how many times a scanline crosses the surface, and that count is only
    meaningful when the surface is closed. An open tube yields an odd count and the fill
    inverts for the rest of the line.

    A boundary edge belongs to exactly one triangle. Walking those edges gives the loops
    bounding each hole; fanning each loop to its own centroid seals it.
    """
    from collections import defaultdict

    use = defaultdict(int)
    for t in range(0, len(idx), 3):
        a, b, c = idx[t], idx[t + 1], idx[t + 2]
        for u, v in ((a, b), (b, c), (c, a)):
            use[(min(u, v), max(u, v))] += 1
    boundary = [e for e, n in use.items() if n == 1]
    if not boundary:
        return verts, idx, 0, 0

    adj = defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)

    verts, idx = list(verts), list(idx)
    used, capped = set(), 0
    for edge in boundary:
        if edge in used:
            continue
        start, nxt = edge
        used.add(edge)
        loop, prev, cur = [start], start, nxt
        while cur != start:
            loop.append(cur)
            step = None
            for cand in adj[cur]:
                if cand == prev:
                    continue
                e = (min(cur, cand), max(cur, cand))
                if e not in used:
                    step = cand
                    break
            if step is None:
                break                      # dead end: not a closed loop, leave it
            used.add((min(cur, step), max(cur, step)))
            prev, cur = cur, step
        if cur != start or len(loop) < 3:
            continue
        cx = sum(verts[i][0] for i in loop) / len(loop)
        cy = sum(verts[i][1] for i in loop) / len(loop)
        cz = sum(verts[i][2] for i in loop) / len(loop)
        centre = len(verts)
        verts.append((cx, cy, cz))
        for k in range(len(loop)):
            idx.extend([centre, loop[k], loop[(k + 1) % len(loop)]])
        capped += 1

    # Count what is still open. A branching tree cut by the crop box shares vertices
    # between several loops, so one pass can dead-end; the caller iterates.
    use2 = defaultdict(int)
    for t in range(0, len(idx), 3):
        a, b, c = idx[t], idx[t + 1], idx[t + 2]
        for u, v in ((a, b), (b, c), (c, a)):
            use2[(min(u, v), max(u, v))] += 1
    remaining = sum(1 for n in use2.values() if n == 1)
    return verts, idx, capped, remaining


def main():
    os.makedirs(OUT, exist_ok=True)

    # First pass: heart wall centroid defines the origin for everything.
    wall = load_stl(os.path.join(SRC, "FMA7274.stl"))
    sx = sy = sz = 0.0
    n = 0
    for tri in wall:
        for p in tri:
            sx += p[0]; sy += p[1]; sz += p[2]; n += 1
    origin = (sx / n, sy / n, sz / n)
    print(f"heart origin (mm, LPS): {origin[0]:.1f}, {origin[1]:.1f}, {origin[2]:.1f}")

    manifest = []
    total_bytes = 0
    for fid, (name, layer, _) in STRUCTURES.items():
        path = os.path.join(SRC, fid + ".stl")
        if not os.path.exists(path):
            print(f"  skip {fid} ({name}) - not downloaded")
            continue
        tris = load_stl(path)
        grid = CLUSTER_MM.get(fid, WELD_MM)
        verts, idx = build_indexed(tris, grid)

        # recentre on the heart
        verts = [(v[0] - origin[0], v[1] - origin[1], v[2] - origin[2]) for v in verts]

        # crop away anatomy outside the mediastinal window
        (x0, x1), (y0, y1), (z0, z1) = CROP_BOX.get(fid, DEFAULT_CROP)
        def inside(v):
            return x0 <= v[0] <= x1 and y0 <= v[1] <= y1 and z0 <= v[2] <= z1
        kept, remap, newverts = [], {}, []
        for t in range(0, len(idx), 3):
            tri = idx[t:t+3]
            if not all(inside(verts[j]) for j in tri):
                continue
            for j in tri:
                if j not in remap:
                    remap[j] = len(newverts)
                    newverts.append(verts[j])
                kept.append(remap[j])
        dropped = len(idx)//3 - len(kept)//3
        verts, idx = newverts, kept

        # Seal whatever the crop (or the source data) left open, but only where the app
        # needs a closed surface. Repeated because a single pass can dead-end on loops
        # that share a vertex, and each pass that closes something changes the edge
        # counts for the next.
        capped = 0
        if layer in FILLED_LAYERS:
            for _ in range(6):
                verts, idx, n, _ = cap_holes(verts, idx)
                capped += n
                if n == 0:
                    break
        # Measured unconditionally. Reporting an uncapped vessel as watertight would be
        # a lie in the manifest and would disarm the renderer's fallback for any future
        # mesh that does get filled.
        open_edges = count_open_edges(idx)

        blob = bytearray()
        blob += b"TEMESH01"
        blob += struct.pack("<II", len(verts), len(idx) // 3)
        for v in verts:
            blob += struct.pack("<fff", *v)
        for i in idx:
            blob += struct.pack("<I", i)
        outpath = os.path.join(OUT, fid + ".temesh")
        with open(outpath, "wb") as f:
            f.write(blob)

        xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
        manifest.append({
            "id": fid, "name": name, "layer": layer,
            "vertexCount": len(verts), "triangleCount": len(idx) // 3,
            # The echo renderer fills tissue by crossing-count parity, which is only
            # meaningful on a closed surface. Record what could not be sealed so the app
            # can fall back to outlining that structure instead of filling it with
            # garbage. Branching vessel trees cut by the crop box keep a few non-manifold
            # junctions that hole-walking cannot resolve.
            "watertight": open_edges == 0,
            "openEdges": open_edges,
            "bounds": {"min": [min(xs), min(ys), min(zs)],
                       "max": [max(xs), max(ys), max(zs)]},
        })
        total_bytes += len(blob)
        print(f"  {fid:11} {name:22} {len(tris):7} -> {len(idx)//3:7} tris  "
              f"{len(blob)/1024:7.0f} KB"
              + (f"  cropped {dropped}" if dropped else "")
              + (f"  capped {capped} holes" if capped else "")
              + (f"  STILL OPEN: {open_edges} edges" if open_edges else ""))

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump({"origin": list(origin), "units": "mm",
                   "axes": {"x": "left", "y": "posterior", "z": "superior"},
                   "structures": manifest}, f, indent=2)
    print(f"total: {total_bytes/1024/1024:.1f} MB across {len(manifest)} structures")


if __name__ == "__main__":
    main()
