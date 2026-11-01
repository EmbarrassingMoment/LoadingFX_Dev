"""
Shared by export_sample.py (UE 5.8 workbench) and build_sample.py (UE 5.5): where the sample's
source text lives, and structural summaries of that text, so a rebuilt asset can be compared
with the text it was built from.

Each asset is a folder under Plugins/DevSampleTools/Sample/ named after the asset:

  Asset.json        path, kind (WidgetBlueprint, Blueprint or Level), parent class, function and event graph names
  Variables.txt     UBlueprint::NewVariables as property text (defaults taken from the CDO); a map's Level Blueprint's
  WidgetTree.t3d    the widget tree as UMG designer copy text (widget blueprints only)
  Actors.t3d        the level's actors as level editor copy text (maps only)
  <Graph>.t3d       every node of a function or event graph as graph editor copy text
"""
import json
import os
import re

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(os.path.dirname(TOOLS_DIR), "Sample")


def asset_dir(asset_name):
    return os.path.join(SAMPLE_DIR, asset_name)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    # Unreal writes CRLF; the repository stores text as LF (.gitattributes), so write LF.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace("\r\n", "\n"))


def read_manifest(asset_name):
    return json.loads(read_text(os.path.join(asset_dir(asset_name), "Asset.json")))


def write_manifest(asset_name, manifest):
    write_text(os.path.join(asset_dir(asset_name), "Asset.json"), json.dumps(manifest, indent=2) + "\n")


def list_assets():
    return sorted(name for name in os.listdir(SAMPLE_DIR)
                  if os.path.isfile(os.path.join(SAMPLE_DIR, name, "Asset.json")))


# --- T3D parsing -------------------------------------------------------------------------

_BEGIN = re.compile(r'^Begin (?:Object|Actor)(?: Class=(\S+))? Name="?([^"\s]+)"?')
_FRAME = {"Begin Map", "End Map", "Begin Level", "End Level", "Begin Surface", "End Surface"}


def parse_t3d(text):
    """Top-level objects of copy text as [{"class", "name", "props": [line], "children": [...]}].
    A "Begin Object Name=..." without a class reopens a sibling declared before it (how subobjects
    get their properties), so its lines are merged into that sibling. Level text's Map / Level / Surface
    frames are skipped, so its actors come out as the top-level objects."""
    root = {"class": None, "name": None, "props": [], "children": []}
    stack = [root]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in _FRAME:
            continue
        m = _BEGIN.match(line)
        if m:
            cls, name = m.group(1), m.group(2)
            parent = stack[-1]
            obj = next((c for c in parent["children"] if c["name"] == name), None) if cls is None else None
            if obj is None:
                obj = {"class": cls, "name": name, "props": [], "children": []}
                parent["children"].append(obj)
            stack.append(obj)
        elif line in ("End Object", "End Actor"):
            stack.pop()
        else:
            stack[-1]["props"].append(line)
    return root["children"]


def short_class(path):
    return path.rsplit(".", 1)[-1].strip("'\"") if path else None


_PIN_ID = re.compile(r"PinId=([0-9A-F]{32})")
_PIN_NAME = re.compile(r'PinName="([^"]*)"')
_PIN_DEFAULT = re.compile(r'DefaultValue="((?:[^"\\]|\\.)*)"')
_PIN_DIR = re.compile(r'Direction="(EGPD_\w+)"')
_LINKED = re.compile(r"LinkedTo=\(([^)]*)\)")
_MEMBER_NAME = re.compile(r'MemberName="([^"]*)"')
_NODE_KEYS = ("FunctionReference", "VariableReference", "EventReference", "CustomClass",
              "ComponentPropertyName", "DelegatePropertyName", "DelegateOwnerClass", "CustomFunctionName")


def graph_summary(text):
    """(nodes, links, defaults): nodes maps node name -> (class, sorted member keys); links is a set
    of "Node.Pin -> Node.Pin" from outputs to inputs; defaults a set of "Node.Pin = value" for
    unlinked inputs. Positions, GUIDs and pin types are left out, so the summary only changes
    when the graph's logic does."""
    objects = parse_t3d(text)
    nodes, pins = {}, {}
    for obj in objects:
        keys = []
        for prop in obj["props"]:
            key = prop.split("=", 1)[0]
            if key in _NODE_KEYS:
                m = _MEMBER_NAME.search(prop)
                value = m.group(1) if m else short_class(prop.split("=", 1)[1])
                keys.append(f"{key}={value}")
        nodes[obj["name"]] = (short_class(obj["class"]), tuple(sorted(keys)))
        for prop in obj["props"]:
            if prop.startswith("CustomProperties Pin "):
                pin_id, pin_name = _PIN_ID.search(prop), _PIN_NAME.search(prop)
                if pin_id and pin_name:
                    pins[pin_id.group(1)] = (obj["name"], pin_name.group(1), prop)

    links, defaults = set(), set()
    for node, pin, prop in pins.values():
        direction = _PIN_DIR.search(prop)
        is_output = bool(direction and direction.group(1) == "EGPD_Output")
        linked = _LINKED.search(prop)
        targets = [t.split() for t in linked.group(1).split(",") if t.strip()] if linked else []
        for target_node, target_pin_id in targets:
            target = pins.get(target_pin_id)
            target_pin = target[1] if target else f"?{target_pin_id}"
            if is_output:
                links.add(f"{node}.{pin} -> {target_node}.{target_pin}")
            else:
                links.add(f"{target_node}.{target_pin} -> {node}.{pin}")
        default = _PIN_DEFAULT.search(prop)
        if default and not targets and not is_output:
            defaults.add(f"{node}.{pin} = {default.group(1)}")
    return nodes, links, defaults


def widget_summary(text):
    """Maps widget name -> (class, frozenset of its property lines), for the widgets of a tree.
    Slots are summarized under "<widget>/<slot>" with the slot's own property lines."""
    widgets = {}
    for obj in parse_t3d(text):
        cls = short_class(obj["class"])
        if cls == "WidgetSlotPair":
            continue
        widgets[obj["name"]] = (cls, frozenset(obj["props"]))
        for child in obj["children"]:
            widgets[f'{obj["name"]}/{child["name"]}'] = (short_class(child["class"]), frozenset(child["props"]))
    return widgets


# Lines that differ between engine versions without the level being different, left out of level comparisons:
# cached derived data, the empty CustomProperties line 5.8 writes for a mesh component, 5.8's name for the cloud
# material property (5.5 calls it Material; the template's cloud uses the default material in both), and the
# spawn collision setting, which only applies when an actor is spawned at runtime.
_VERSION_LINES = ("StaticMeshDerivedDataKey=", "MaterialLifetimePtr=", "SpawnCollisionHandlingMethod=")


def _level_props(obj):
    """An actor's or component's property lines without the version-dependent ones. A line that only points at one of
    the actor's own components (SpriteComponent="Sprite") is left out too: whether it is written depends on the
    version's defaults, and the components themselves are compared on their own."""
    children = {child["name"] for child in obj["children"]}
    props = []
    for p in obj["props"]:
        value = p.split("=", 1)[1].strip('"') if "=" in p else None
        if p.startswith(_VERSION_LINES) or p.strip() == "CustomProperties" or value in children:
            continue
        props.append(p)
    return frozenset(props)


def level_summary(text):
    """Maps actor label -> (class, frozenset of its property lines), and "<label>/<component>" -> the
    component's (class, property lines). Pasting may rename actors, so labels are the keys."""
    actors = {}
    for obj in parse_t3d(text):
        label = next((p.split("=", 1)[1].strip('"') for p in obj["props"] if p.startswith("ActorLabel=")), obj["name"])
        actors[label] = (short_class(obj["class"]), _level_props(obj))
        for child in obj["children"]:
            actors[f"{label}/{child['name']}"] = (short_class(child["class"]), _level_props(child))
    return actors


def split_top_level(text):
    """Splits "a,b,(c,d)" at the commas outside parentheses and quotes."""
    parts, depth, quoted, start = [], 0, False, 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == "\\":
                i += 1
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    if text[start:]:
        parts.append(text[start:])
    return parts


def parse_struct(text):
    """Maps the top-level keys of struct text "(Key=Value,...)" to their raw value text."""
    inner = text.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    fields = {}
    for part in split_top_level(inner):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _unquote(value):
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def _normalize_class_ref(value):
    # 5.8 writes an object path as "/Script/CoreUObject.Class'/Script/Engine.World'"; 5.5 may not.
    return re.sub(r"^[\w/.]+'([^']*)'$", r"\1", _unquote(value))


def variable_summary(text):
    """Maps variable name -> (pin category, sub category object, container, default value, property flags)."""
    result = {}
    for entry in split_top_level(text.strip()[1:-1]):
        fields = parse_struct(entry)
        var_type = parse_struct(fields.get("VarType", "()"))
        result[_unquote(fields.get("VarName", ""))] = (
            _unquote(var_type.get("PinCategory", "")),
            _normalize_class_ref(var_type.get("PinSubCategoryObject", "")),
            var_type.get("ContainerType", ""),
            _unquote(fields.get("DefaultValue", "")),
            fields.get("PropertyFlags", ""),
        )
    return result


def diff_sets(label, expected, actual):
    """Lines describing what is missing from / extra in actual, prefixed with the label."""
    lines = [f"{label} missing: {x}" for x in sorted(set(expected) - set(actual))]
    lines += [f"{label} extra: {x}" for x in sorted(set(actual) - set(expected))]
    return lines
