"""
S-expression parser and serializer for KiCad files.

Handles .kicad_sym and .kicad_mod formats.  Parses text into a tree of
SExprNode objects, which can be queried, modified, and serialized back to text.
"""

import re
import uuid


class SExprNode:
    """A node in an S-expression tree.

    Each node has a tag (the first atom after the opening paren), a list of
    values (subsequent atoms before any child nodes), and a list of children
    (nested S-expressions).

    Example: (pin power_in line ...) → tag="pin", values=["power_in", "line"]
    """

    __slots__ = ("tag", "values", "children")

    def __init__(self, tag="", values=None, children=None):
        self.tag = tag
        self.values = values or []
        self.children = children or []

    def find_child(self, tag):
        """Return the first child with the given tag, or None."""
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def find_all(self, tag):
        """Return all direct children with the given tag."""
        return [c for c in self.children if c.tag == tag]

    def find_recursive(self, tag):
        """Return all descendants (any depth) with the given tag."""
        results = []
        for c in self.children:
            if c.tag == tag:
                results.append(c)
            results.extend(c.find_recursive(tag))
        return results

    def get_value(self, index=0):
        """Get a value by index, or None if out of range."""
        if index < len(self.values):
            return self.values[index]
        return None

    def set_value(self, index, value):
        """Set a value at the given index, extending with empty strings if needed."""
        while len(self.values) <= index:
            self.values.append("")
        self.values[index] = value

    def get_property(self, name):
        """Get the value of a KiCad property by name. Returns None if not found."""
        for c in self.children:
            if c.tag == "property" and c.get_value(0) == name:
                return c.get_value(1)
        return None

    def set_property(self, name, value):
        """Set the value of a KiCad property by name. Does nothing if not found."""
        for c in self.children:
            if c.tag == "property" and c.get_value(0) == name:
                c.set_value(1, value)
                return True
        return False

    def remove_child(self, child):
        """Remove a child node."""
        self.children.remove(child)

    def add_child(self, child):
        """Append a child node."""
        self.children.append(child)

    def clone(self):
        """Deep copy of this node and all descendants."""
        new = SExprNode(self.tag, list(self.values))
        new.children = [c.clone() for c in self.children]
        return new

    def __repr__(self):
        return f"SExprNode({self.tag!r}, values={self.values!r}, children={len(self.children)})"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Matches: ( ) "quoted string" or bare-atom
_TOKEN_RE = re.compile(r"""
    (?P<OPEN>\()
  | (?P<CLOSE>\))
  | (?P<STRING>"(?:[^"\\]|\\.)*")
  | (?P<ATOM>[^\s()"]+)
""", re.VERBOSE)


def _tokenize(text):
    """Yield (type, value) tokens from S-expression text."""
    for m in _TOKEN_RE.finditer(text):
        if m.group("OPEN"):
            yield ("OPEN", "(")
        elif m.group("CLOSE"):
            yield ("CLOSE", ")")
        elif m.group("STRING"):
            yield ("ATOM", m.group("STRING"))
        elif m.group("ATOM"):
            yield ("ATOM", m.group("ATOM"))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse(text):
    """Parse S-expression text into a list of SExprNode trees.

    Returns a list because a file may contain multiple top-level expressions,
    though KiCad files typically have one.
    """
    tokens = list(_tokenize(text))
    pos = [0]  # mutable index

    def _parse_node():
        # We just consumed an OPEN token
        if pos[0] >= len(tokens):
            raise ValueError("Unexpected end of input after '('")

        # First atom is the tag; handle nested parens gracefully
        if tokens[pos[0]][0] == "CLOSE":
            # Empty expression () — skip it
            pos[0] += 1
            return SExprNode("")
        if tokens[pos[0]][0] != "ATOM":
            raise ValueError(
                f"Malformed S-expression: expected tag name after '(', "
                f"got '{tokens[pos[0]][1]}'"
            )
        tag_token = tokens[pos[0]][1]
        tag = _unquote(tag_token)
        pos[0] += 1

        node = SExprNode(tag)

        # Read values and children until CLOSE
        while pos[0] < len(tokens):
            ttype, tval = tokens[pos[0]]
            if ttype == "CLOSE":
                pos[0] += 1
                return node
            elif ttype == "OPEN":
                pos[0] += 1
                child = _parse_node()
                node.children.append(child)
            elif ttype == "ATOM":
                node.values.append(_unquote(tval))
                pos[0] += 1
            else:
                raise ValueError(f"Unexpected token: {tokens[pos[0]]}")

        raise ValueError("Unterminated S-expression")

    nodes = []
    while pos[0] < len(tokens):
        ttype, tval = tokens[pos[0]]
        if ttype == "OPEN":
            pos[0] += 1
            nodes.append(_parse_node())
        else:
            pos[0] += 1  # skip stray atoms at top level

    return nodes


def parse_file(path):
    """Parse a KiCad file and return the list of top-level nodes."""
    with open(path, "r", encoding="utf-8") as f:
        return parse(f.read())


def _unquote(s):
    """Remove surrounding quotes from a token if present."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"')
    return s


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

# Tags where the content should stay on one line for readability
_INLINE_TAGS = {
    "at", "size", "stroke", "fill", "effects", "font", "justify",
    "offset", "length", "width", "type", "color", "xy",
    "exclude_from_sim", "in_bom", "on_board", "hide",
    "number", "name", "layers", "roundrect_rratio", "net",
    "layer", "tstamp", "uuid",
}


def serialize(nodes, indent=0):
    """Serialize a list of SExprNode trees back to S-expression text."""
    parts = []
    for node in nodes:
        parts.append(_serialize_node(node, indent))
    return "\n".join(parts) + "\n"


# Bare keywords that KiCad writes unquoted
_BARE_KEYWORDS = {
    "yes", "no", "none", "default", "background",
    "line", "inverted", "clock", "inverted_clock", "input_low",
    "clock_low", "output_low", "edge_clock_high", "non_logic",
    "input", "output", "bidirectional", "tri_state", "passive",
    "power_in", "power_out", "open_collector", "open_emitter",
    "no_connect", "unspecified", "free",
    "smd", "thru_hole", "roundrect", "rect", "circle", "oval", "custom",
    "left", "right", "top", "bottom", "mirror",
}


def _is_bare(s):
    """Check if a value should be written bare (unquoted)."""
    if not s:
        return False
    if s in _BARE_KEYWORDS:
        return True
    # Pure numbers (integers and floats, possibly negative)
    if re.match(r"^-?\d+(\.\d+)?$", s):
        return True
    return False


def _quote(s):
    """Quote a string for S-expression output.  Bare keywords and numbers stay unquoted."""
    if _is_bare(s):
        return s
    return _force_quote(s)


def _force_quote(s):
    """Always quote a string, regardless of content."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Tags whose values must always be quoted (even if they look like numbers)
_ALWAYS_QUOTE_VALUES = {"name", "number", "property", "generator",
                        "descr", "uri", "options", "net"}


def _serialize_node(node, indent):
    """Serialize a single node, choosing inline vs. multiline format."""
    # Check if this should be inline
    if node.tag in _INLINE_TAGS or (not node.children and len(node.values) <= 3):
        return _serialize_inline(node, indent)

    # For nodes with property tag and short content, inline
    if node.tag == "property" and not node.children:
        return _serialize_inline(node, indent)

    # Multiline format
    prefix = "\t" * indent
    quote_fn = _force_quote if node.tag in _ALWAYS_QUOTE_VALUES else _quote
    parts = [f"{prefix}({node.tag}"]
    for v in node.values:
        parts[0] += " " + quote_fn(v)

    lines = [parts[0]]
    for child in node.children:
        lines.append(_serialize_node(child, indent + 1))
    lines.append(f"{prefix})")
    return "\n".join(lines)


def _serialize_inline(node, indent):
    """Serialize a node as a single line."""
    prefix = "\t" * indent
    quote_fn = _force_quote if node.tag in _ALWAYS_QUOTE_VALUES else _quote
    parts = [node.tag]
    for v in node.values:
        parts.append(quote_fn(v))
    for child in node.children:
        # Inline children recursively
        child_str = _serialize_inline(child, 0).strip()
        parts.append(child_str)
    return f"{prefix}({' '.join(parts)})"


def serialize_to_file(nodes, path):
    """Serialize and write to a file."""
    text = serialize(nodes)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def regenerate_uuids(node):
    """Replace all UUIDs in a node tree with fresh ones."""
    for uuid_node in node.find_recursive("uuid"):
        uuid_node.values = [str(uuid.uuid4())]
    for tstamp_node in node.find_recursive("tstamp"):
        tstamp_node.values = [str(uuid.uuid4())]


def new_uuid():
    """Generate a new UUID string."""
    return str(uuid.uuid4())
