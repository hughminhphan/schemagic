"""
Footprint modifier: clone an existing KiCad footprint and optionally modify it.

For most use cases, footprints are used as-is from the KiCad library.
This module handles copying them to the project-local library.
"""

import os
import re
import shutil
from typing import Optional

from ..core.config import FOOTPRINT_DIR, MODEL_DIR
from .sexpr import parse_file, serialize, regenerate_uuids, SExprNode


def clone_footprint(source_lib: str, source_name: str, dest_dir: str,
                    new_name: str = None):
    """Copy a footprint from the KiCad library to a project-local library.

    Args:
        source_lib: library name (e.g. "Package_TO_SOT_SMD")
        source_name: footprint name (e.g. "SOT-23-6")
        dest_dir: path to the destination .pretty directory
        new_name: optional new name for the footprint file

    Returns:
        str: path to the copied .kicad_mod file
    """
    if not FOOTPRINT_DIR:
        raise FileNotFoundError(
            "KiCad footprint libraries not found. Check your KiCad installation."
        )
    source_path = os.path.join(FOOTPRINT_DIR, f"{source_lib}.pretty",
                               f"{source_name}.kicad_mod")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Footprint not found: {source_path}")

    os.makedirs(dest_dir, exist_ok=True)
    fp_name = new_name or source_name
    dest_path = os.path.join(dest_dir, f"{fp_name}.kicad_mod")

    if new_name and new_name != source_name:
        # Parse, rename, re-serialize
        nodes = parse_file(source_path)
        if nodes:
            root = nodes[0]
            root.set_value(0, new_name)
            regenerate_uuids(root)
            text = serialize(nodes)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(text)
    else:
        # Simple copy
        shutil.copy2(source_path, dest_path)

    return dest_path


def read_model_ref(fp_path: str) -> Optional[str]:
    """Extract the 3D model path from a .kicad_mod file.

    Returns the model path with the KiCad env var prefix stripped
    (e.g. "Package_SO.3dshapes/SOIC-8.wrl"), or None if no model node found.
    """
    if not os.path.isfile(fp_path):
        return None

    nodes = parse_file(fp_path)
    if not nodes:
        return None

    root = nodes[0]
    model_node = root.find_child("model")
    if not model_node:
        return None

    raw_path = model_node.get_value(0)
    if not raw_path:
        return None

    # Strip KiCad env var prefixes like ${KICAD8_3DMODEL_DIR}/
    cleaned = re.sub(r'\$\{[^}]+\}/', '', raw_path)
    return cleaned


def inject_model_ref(fp_path: str, source_lib: str, source_name: str) -> Optional[str]:
    """Inject a (model ...) node into a footprint that lacks one.

    Infers the 3D model path from the footprint library/name convention:
    Package_SO.pretty/X.kicad_mod -> Package_SO.3dshapes/X.wrl

    If MODEL_DIR is available, validates the file exists before injecting.
    Returns the injected model ref (stripped), or None if injection failed.
    """
    if not os.path.isfile(fp_path):
        return None

    # Derive the expected 3D model path
    shapes_dir = source_lib.replace(".pretty", ".3dshapes")
    model_filename = f"{source_name}.wrl"
    model_rel = f"{shapes_dir}/{model_filename}"
    model_kicad_path = f"${{KICAD8_3DMODEL_DIR}}/{model_rel}"

    # Validate the 3D model file exists if we have access to the model dir
    if MODEL_DIR:
        expected_path = os.path.join(MODEL_DIR, shapes_dir, model_filename)
        if not os.path.isfile(expected_path):
            # Try .step as fallback
            step_filename = f"{source_name}.step"
            step_path = os.path.join(MODEL_DIR, shapes_dir, step_filename)
            if os.path.isfile(step_path):
                model_filename = step_filename
                model_rel = f"{shapes_dir}/{model_filename}"
                model_kicad_path = f"${{KICAD8_3DMODEL_DIR}}/{model_rel}"
            else:
                return None  # No matching 3D model found

    # Parse the footprint and inject the model node
    nodes = parse_file(fp_path)
    if not nodes:
        return None

    root = nodes[0]

    # Build (model "path" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
    model = SExprNode("model", [model_kicad_path])

    for attr_name in ("offset", "scale", "rotate"):
        xyz = SExprNode("xyz", ["0", "0", "0"])
        attr = SExprNode(attr_name)
        attr.add_child(xyz)
        model.add_child(attr)

    # Set scale to 1 1 1
    scale_node = model.find_child("scale")
    if scale_node:
        xyz_node = scale_node.find_child("xyz")
        if xyz_node:
            xyz_node.values = ["1", "1", "1"]

    root.add_child(model)

    text = serialize(nodes)
    with open(fp_path, "w", encoding="utf-8") as f:
        f.write(text)

    return model_rel
