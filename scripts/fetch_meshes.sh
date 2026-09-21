#!/bin/bash
#
# Download the BodyParts3D source meshes that scripts/build_meshes.py consumes.
#
#   BodyParts3D, (c) The Database Center for Life Science licensed under
#   CC Attribution-Share Alike 2.1 Japan
#   https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html
#
# The files come from a community mirror of the DBCLS data. Run from the repository
# root; they are written to Assets/BodyParts3D/ (git-ignored, ~32 MB). Anything already
# downloaded is skipped, and an HTTP error stops the script rather than saving the error
# page as a mesh.

set -euo pipefail

BASE_URL="https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/assets/BodyParts3D_data/stl"
OUTPUT_DIR="Assets/BodyParts3D"

# Exactly the structures listed in STRUCTURES in scripts/build_meshes.py.
IDS=(
    FMA7274     # wall of heart (carries all four chamber cavities)
    FMA7235     # mitral valve
    FMA7234     # tricuspid valve
    FMA7246     # pulmonary valve
    FMA3736     # ascending aorta
    FMA3768     # aortic arch
    FMA3784     # descending aorta
    FMA4720     # superior vena cava
    FMA10951    # inferior vena cava
    FMA66326    # pulmonary artery
    FMA66643    # pulmonary veins
    FMA4706     # coronary sinus
    FMA7260     # RV anterior papillary muscle
    FMA7261     # RV posterior papillary muscle
    FMA7262     # RV septal papillary muscle
    FMA7266     # LV posterior papillary muscle
    FMA9352nsn  # LV papillary muscle
)

mkdir -p "$OUTPUT_DIR"

for id in "${IDS[@]}"; do
    dest="$OUTPUT_DIR/$id.stl"
    if [ -f "$dest" ]; then
        echo "$id.stl already exists, skipping."
        continue
    fi
    echo "Downloading $id.stl..."
    curl -fL --retry 3 --silent --show-error "$BASE_URL/$id.stl" -o "$dest.part"
    mv "$dest.part" "$dest"
done

echo "Done. ${#IDS[@]} source meshes are in $OUTPUT_DIR"
