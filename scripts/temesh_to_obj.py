#!/usr/bin/env python3
"""
Convert the .temesh files in Assets/HeartMeshes/ to Wavefront OBJ, an open format that
Blender, MeshLab and most other 3D tools read directly.

.temesh is a deliberately trivial binary layout (see README.md), so this needs nothing
but the standard library.

Each OBJ carries the BodyParts3D credit and licence in its header, so the attribution
travels with the file if it is copied out of this repository.

Usage:  python3 scripts/temesh_to_obj.py [SRC_DIR] [OUT_DIR]
        (defaults: Assets/HeartMeshes  obj)
"""
import json
import os
import struct
import sys

CREDIT = ("BodyParts3D, (c) The Database Center for Life Science licensed under "
          "CC Attribution-Share Alike 2.1 Japan")
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/2.1/jp/"


def read_temesh(path):
    """Return (vertices, indices): flat float lists/tuples of x,y,z and 0-based triangle ids."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"TEMESH01":
        raise ValueError(f"{path}: not a TEMESH01 file")
    vertex_count, triangle_count = struct.unpack_from("<II", data, 8)
    header = 16
    position_bytes = vertex_count * 3 * 4
    index_bytes = triangle_count * 3 * 4
    if len(data) < header + position_bytes + index_bytes:
        raise ValueError(f"{path}: truncated")
    positions = struct.unpack_from(f"<{vertex_count * 3}f", data, header)
    indices = struct.unpack_from(f"<{triangle_count * 3}I", data, header + position_bytes)
    return positions, indices


def write_obj(path, name, structure_id, positions, indices):
    vertex_count = len(positions) // 3
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {name} ({structure_id})\n")
        f.write(f"# {CREDIT}\n")
        f.write(f"# Licence: {LICENCE_URL}\n")
        f.write("# Modified from the original: see README.md in this repository.\n")
        f.write("# Units: millimetres. +X = patient left, +Y = posterior, +Z = superior.\n")
        f.write("# Origin: centroid of the heart wall.\n")
        f.write(f"o {name.replace(' ', '_')}\n")
        for i in range(vertex_count):
            x, y, z = positions[i * 3:i * 3 + 3]
            f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for t in range(0, len(indices), 3):
            a, b, c = indices[t] + 1, indices[t + 1] + 1, indices[t + 2] + 1   # OBJ is 1-based
            f.write(f"f {a} {b} {c}\n")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "Assets/HeartMeshes"
    out = sys.argv[2] if len(sys.argv) > 2 else "obj"
    os.makedirs(out, exist_ok=True)

    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as f:
        structures = json.load(f)["structures"]

    for s in structures:
        positions, indices = read_temesh(os.path.join(src, s["id"] + ".temesh"))
        assert len(positions) // 3 == s["vertexCount"], f"{s['id']}: vertex count mismatch"
        assert len(indices) // 3 == s["triangleCount"], f"{s['id']}: triangle count mismatch"
        write_obj(os.path.join(out, s["id"] + ".obj"), s["name"], s["id"], positions, indices)
        print(f"  {s['id']:11} {s['name']:22} {s['triangleCount']:7} triangles")
    print(f"wrote {len(structures)} OBJ files to {out}/")


if __name__ == "__main__":
    main()
