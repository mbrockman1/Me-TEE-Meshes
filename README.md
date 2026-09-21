# Me-TEE-Meshes

The heart and great-vessel 3D models used by **MeTEE**, an iOS teaching simulator for
transesophageal echocardiography (TEE), published here as free content so anyone can
download, use and adapt them.

> BodyParts3D, © The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan

These models are **adapted from [BodyParts3D](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html)**
and are licensed under the same terms, **CC BY-SA 2.1 Japan**. You may use, share and adapt
them, including commercially, provided you credit BodyParts3D as above, indicate any changes
you make, and license your adaptation under the same terms. See [LICENSE.md](LICENSE.md).

## What is here

| Path | Contents |
| --- | --- |
| `Assets/HeartMeshes/` | the 17 processed meshes as `.temesh`, plus `manifest.json` |
| `obj/` | the same meshes as Wavefront OBJ, for Blender, MeshLab and most 3D tools |
| `scripts/` | how they were made: fetch the sources, build, convert |

| ID | Structure | Layer | Triangles |
| --- | --- | --- | ---: |
| `FMA7274` | Wall of Heart | myocardium | 145,904 |
| `FMA7235` | Mitral Valve | valves | 14,102 |
| `FMA7234` | Tricuspid Valve | valves | 10,366 |
| `FMA7246` | Pulmonary Valve | valves | 17,390 |
| `FMA3736` | Ascending Aorta | greatVessels | 2,148 |
| `FMA3768` | Aortic Arch | greatVessels | 3,274 |
| `FMA3784` | Descending Aorta | greatVessels | 11,864 |
| `FMA4720` | Superior Vena Cava | greatVessels | 1,532 |
| `FMA10951` | Inferior Vena Cava | greatVessels | 2,969 |
| `FMA66326` | Pulmonary Artery | greatVessels | 22,120 |
| `FMA66643` | Pulmonary Veins | greatVessels | 16,539 |
| `FMA4706` | Coronary Sinus | greatVessels | 1,900 |
| `FMA7260` | RV Anterior Papillary | chambers | 3,702 |
| `FMA7261` | RV Posterior Papillary | chambers | 2,626 |
| `FMA7262` | RV Septal Papillary | chambers | 1,854 |
| `FMA7266` | LV Posterior Papillary | chambers | 3,832 |
| `FMA9352nsn` | LV Papillary Muscle | chambers | 3,984 |
| | **Total** | | **266,106** |

Units are millimetres. Axes follow the source data: +X patient left, +Y posterior,
+Z superior. The origin is the centroid of the heart wall
(at 16.1, -122.8, 1235.7 mm in the source coordinates; also in `manifest.json`).

## Changes made to the original

BodyParts3D is a whole-body atlas. These files differ from it as follows:

1. **Selection.** 17 structures were taken from the atlas.
2. **Simplification.** Duplicate vertices were welded and the mesh was clustered onto a grid:
   0.35 mm by default, coarser for the heart wall (0.9 mm), tricuspid valve (0.8 mm),
   descending aorta (0.9 mm) and pulmonary arteries and veins (1.4 mm). The heart wall went
   from 331,592 to 145,904 triangles.
3. **Re-centring** on the centroid of the heart wall.
4. **Cropping** to a window around the heart. The pulmonary arteries and veins are trimmed back
   to the lung hila.
5. **Hole sealing.** For the heart wall, valves and papillary muscles, open boundaries were
   closed with added triangle fans. These are artificial flat faces that are not in the
   original.
6. **Conversion** to the `.temesh` and OBJ formats, and a `layer` label per structure in
   `manifest.json` (`myocardium`, `valves`, `chambers`, `greatVessels`). The layer labels are
   ours, not BodyParts3D's.

Every step is in [`scripts/build_meshes.py`](scripts/build_meshes.py). No mesh was edited by
hand, and rebuilding from the source files reproduces the files in `Assets/HeartMeshes/`
byte for byte.

## Formats

### `.temesh`

Little-endian, no padding:

| Bytes | Type | Meaning |
| --- | --- | --- |
| 0 to 7 | ASCII | `TEMESH01` |
| 8 to 11 | uint32 | vertex count `V` |
| 12 to 15 | uint32 | triangle count `T` |
| 16 onward | float32 x 3V | vertex positions x, y, z in millimetres |
| then | uint32 x 3T | triangle vertex indices, 0-based |

```python
import struct
data = open("Assets/HeartMeshes/FMA7274.temesh", "rb").read()
assert data[:8] == b"TEMESH01"
V, T = struct.unpack_from("<II", data, 8)
positions = struct.unpack_from(f"<{V * 3}f", data, 16)
indices = struct.unpack_from(f"<{T * 3}I", data, 16 + V * 12)
```

### OBJ

Standard Wavefront OBJ (`v` and `f` lines, 1-based indices), one file per structure. The
credit and licence are repeated in each file's header.

## Rebuilding

Needs `bash`, `curl` and `python3` (standard library only). Run from the repository root:

```sh
scripts/fetch_meshes.sh            # downloads the 17 source STLs to Assets/BodyParts3D/ (~32 MB)
python3 scripts/build_meshes.py    # writes Assets/HeartMeshes/*.temesh and manifest.json
python3 scripts/temesh_to_obj.py   # writes obj/*.obj
```

The original STL files are not included here; they are downloaded from a community mirror of
the DBCLS data.

## Citation

Mitsuhashi N, Fujieda K, Tamura T, Kawamoto S, Takagi T, Okubo K. BodyParts3D: 3D structure
database for anatomical concepts. *Nucleic Acids Res.* 2009;37(Database issue):D782-D785.
[doi:10.1093/nar/gkn613](https://doi.org/10.1093/nar/gkn613)

## Disclaimer

MeTEE uses these models to draw a simulated ultrasound cross-section and a 3D view. They come
from a single generic adult atlas, are simplified, and are provided for education only. They
are not for diagnosis or any clinical use, and come with no warranty. This project is not
affiliated with or endorsed by the Database Center for Life Science.
