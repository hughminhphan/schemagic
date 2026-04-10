"""
Library manager: create and manage project-local KiCad libraries.

Creates:
- schemagic.kicad_sym (symbol library, multiple symbols per file)
- schemagic.pretty/ (footprint library, one .kicad_mod per footprint)
- Updates sym-lib-table and fp-lib-table to register the libraries
"""

import os
import re

from .sexpr import parse_file, parse, serialize, SExprNode, new_uuid
from ..core.models import GeneratedComponent


LIB_NAME = "schemagic"
SYM_LIB_FILE = f"{LIB_NAME}.kicad_sym"
FP_LIB_DIR = f"{LIB_NAME}.pretty"


def save_component(project_dir: str, symbol_node: SExprNode,
                   footprint_source_lib: str = "", footprint_source_name: str = "",
                   footprint_node: SExprNode = None) -> GeneratedComponent:
    """Save a generated symbol and footprint to the project-local library.

    Args:
        project_dir: path to the KiCad project directory
        symbol_node: the modified symbol SExprNode
        footprint_source_lib: source library for the footprint
        footprint_source_name: source footprint name
        footprint_node: optional pre-built footprint node (if not copying)

    Returns:
        GeneratedComponent with paths to the saved files
    """
    result = GeneratedComponent()
    sym_name = symbol_node.get_value(0)
    result.symbol_name = sym_name

    # Save symbol
    sym_lib_path = os.path.join(project_dir, SYM_LIB_FILE)
    _save_symbol_to_lib(sym_lib_path, symbol_node)
    result.symbol_lib_path = sym_lib_path

    # Save footprint
    if footprint_source_lib and footprint_source_name:
        from .footprint_modifier import clone_footprint, read_model_ref, inject_model_ref
        fp_dir = os.path.join(project_dir, FP_LIB_DIR)
        fp_path = clone_footprint(footprint_source_lib, footprint_source_name, fp_dir)
        result.footprint_lib_path = fp_dir
        result.footprint_name = footprint_source_name

        # Extract or inject 3D model reference
        model_ref = read_model_ref(fp_path)
        if model_ref:
            result.model_ref = model_ref
        else:
            # Try to inject a model reference by convention
            injected = inject_model_ref(fp_path, footprint_source_lib, footprint_source_name)
            if injected:
                result.model_ref = injected
                result.model_ref_inferred = True

    # Update lib tables
    _ensure_sym_lib_table(project_dir)
    _ensure_fp_lib_table(project_dir)

    return result


def _save_symbol_to_lib(lib_path, symbol_node):
    """Add or replace a symbol in the project-local .kicad_sym library."""
    sym_name = symbol_node.get_value(0)

    # Strip embedded_fonts from cloned symbols (KiCad version mismatch issue)
    ef = symbol_node.find_child("embedded_fonts")
    if ef:
        symbol_node.remove_child(ef)

    if os.path.isfile(lib_path):
        # Load existing library
        nodes = parse_file(lib_path)
        root = nodes[0]

        # Update version to KiCad 10 format
        ver = root.find_child("version")
        if ver:
            ver.set_value(0, "20251024")

        # Remove existing symbol with same name
        for existing in root.find_all("symbol"):
            if existing.get_value(0) == sym_name:
                root.remove_child(existing)
                break

        # Strip embedded_fonts from all existing symbols too
        for existing in root.find_all("symbol"):
            ef = existing.find_child("embedded_fonts")
            if ef:
                existing.remove_child(ef)

        # Add the new symbol
        root.add_child(symbol_node)
    else:
        # Create new library file
        root = SExprNode("kicad_symbol_lib", [])
        root.add_child(SExprNode("version", ["20251024"]))
        root.add_child(SExprNode("generator", ["schemagic"]))
        root.add_child(SExprNode("generator_version", ["1.0"]))
        root.add_child(symbol_node)
        nodes = [root]

    text = serialize(nodes)
    with open(lib_path, "w", encoding="utf-8") as f:
        f.write(text)


def _ensure_sym_lib_table(project_dir):
    """Ensure the project sym-lib-table includes our library."""
    table_path = os.path.join(project_dir, "sym-lib-table")
    _ensure_lib_table(table_path, "sym_lib_table", LIB_NAME,
                      "${KIPRJMOD}/" + SYM_LIB_FILE,
                      "Datasheet-matched symbols from schemagic")


def _ensure_fp_lib_table(project_dir):
    """Ensure the project fp-lib-table includes our library."""
    table_path = os.path.join(project_dir, "fp-lib-table")
    _ensure_lib_table(table_path, "fp_lib_table", LIB_NAME,
                      "${KIPRJMOD}/" + FP_LIB_DIR,
                      "Datasheet-matched footprints from schemagic")


def _ensure_lib_table(table_path, table_tag, lib_name, uri, descr):
    """Ensure a lib table file exists and contains our library entry."""
    if os.path.isfile(table_path):
        nodes = parse_file(table_path)
        if nodes:
            root = nodes[0]
            # Check if our library is already there
            for lib in root.find_all("lib"):
                name_node = lib.find_child("name")
                if name_node and name_node.get_value(0) == lib_name:
                    # Verify URI is correct, update if stale
                    uri_node = lib.find_child("uri")
                    if uri_node and uri_node.get_value(0) == uri:
                        return  # already registered with correct URI
                    # Replace the stale entry
                    root.remove_child(lib)
                    root.add_child(_make_lib_entry(lib_name, uri, descr))
                    text = serialize(nodes)
                    with open(table_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    return
            # Add our entry
            root.add_child(_make_lib_entry(lib_name, uri, descr))
            text = serialize(nodes)
            with open(table_path, "w", encoding="utf-8") as f:
                f.write(text)
            return

    # Create new table file
    root = SExprNode(table_tag, [])
    root.add_child(SExprNode("version", ["7"]))
    root.add_child(_make_lib_entry(lib_name, uri, descr))
    text = serialize([root])
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(text)


def _make_lib_entry(name, uri, descr):
    """Create a (lib ...) node for a lib table."""
    lib = SExprNode("lib")
    lib.add_child(SExprNode("name", [name]))
    lib.add_child(SExprNode("type", ["KiCad"]))
    lib.add_child(SExprNode("uri", [uri]))
    lib.add_child(SExprNode("options", [""]))
    lib.add_child(SExprNode("descr", [descr]))
    return lib
