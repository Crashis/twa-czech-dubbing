"""Extract structural HIRC links and offsets from wwiser's concatenated XML dump."""
from pathlib import Path
from collections import Counter
import xml.etree.ElementTree as ET
import argparse
import json


class WrappedXML:
    def __init__(self, path):
        self.file = path.open("rb")
        self.prefix = True
        self.suffix = False

    def read(self, size=-1):
        if self.prefix:
            self.prefix = False
            return b"<banks>"
        data = self.file.read(size)
        if data:
            return data
        if not self.suffix:
            self.suffix = True
            return b"</banks>"
        return b""


def fields(element, name):
    return [dict(f.attrib) for f in element.iter("field") if f.get("name") == name]


def val(element, name, default=None):
    found = fields(element, name)
    return int(found[0]["value"]) if found else default


def parse_dialogue(element):
    groups = []
    for group in element.iter("object"):
        if group.get("name") == "AkGameSync":
            groups.append({"group": fields(group, "ulGroup")[0], "type": fields(group, "eGroupType")[0]})
    branches = []
    tree = next(o for o in element.iter("object") if o.get("name") == "AkDecisionTree")

    def visit(node, keys):
        key = next(f for f in node.findall("field") if f.get("name") == "key")
        # The root key is a tree sentinel, not a game-sync argument.
        newkeys = keys + [dict(key.attrib)]
        audio = next((f for f in node.findall("field") if f.get("name") == "audioNodeId"), None)
        if audio is not None:
            branches.append({"keys": newkeys[1:], "target": dict(audio.attrib),
                             "weight": val(node, "uWeight"), "probability": val(node, "uProbability")})
        for child_list in node.findall("list"):
            for child in child_list.findall("object"):
                visit(child, newkeys)

    for node in tree.find("list").findall("object"):
        visit(node, [])
    return groups, branches


def parse_graph(input_path):
    stack = []
    banks = {}
    errors = []
    bank = None
    for event, element in ET.iterparse(WrappedXML(Path(input_path)), events=("start", "end")):
        if event == "start":
            stack.append(element)
            if element.tag == "root":
                bank = element.get("filename")
                banks[bank] = {"xml_root": dict(element.attrib), "nodes": [], "header": {}}
            continue
        if element.tag in ("error", "skip"):
            errors.append({"bank": bank, "tag": element.tag, **element.attrib})
        if element.tag == "object" and len(stack) > 1 and stack[-2].get("name") == "listLoadedItem":
            kind = element.get("name")
            id_field = element.find("field[@name='ulID']")
            if id_field is None:
                candidates = [f for f in element.findall("field") if f.get("type") == "sid"]
                assert len(candidates) == 1, (bank, kind, ET.tostring(element, encoding="unicode")[:1400])
                id_field = candidates[0]
            node = {"id": int(id_field.get("value")), "type": kind,
                    "id_offset": int(id_field.get("offset")), "bank": bank,
                    "section_offset": val(element, "eHircType")}
            node["section_offset"] = int(element.find("field[@name='eHircType']").get("offset"))
            node["section_size"] = val(element, "dwSectionSize")
            node["children"] = fields(element, "ulChildID")
            node["actions"] = fields(element, "ulActionID")
            if kind.startswith("CAkAction"):
                node["target"] = fields(element, "idExt")
                node["action_type"] = fields(element, "ulActionType")
                node["bank_target"] = fields(element, "fileID")
            if kind == "CAkSound":
                for name in ["sourceID", "ulPluginID", "StreamType", "uInMemoryMediaSize",
                             "bIsLanguageSpecific", "bPrefetch", "bNonCachable", "bHasSource", "DirectParentID"]:
                    node[name] = fields(element, name)
            if kind == "CAkRanSeqCntr":
                node["mode"] = fields(element, "eMode")
                node["playlist"] = [{"target": fields(o, "ulPlayID")[0], "weight": val(o, "weight")}
                                    for o in element.iter("object") if o.get("name") == "AkPlaylistItem"]
                node["loop"] = {name: fields(element, name) for name in
                                ["sLoopCount", "sLoopModMin", "sLoopModMax", "bIsContinuous", "eTransitionMode"]}
            if kind == "CAkDialogueEvent":
                node["groups"], node["branches"] = parse_dialogue(element)
                node["depth"] = val(element, "uTreeDepth")
                assert all(len(branch["keys"]) == node["depth"] for branch in node["branches"])
            # Preserve sound/container property bundles, including inherited mute/loop flags.
            node["properties"] = []
            for obj in element.iter("object"):
                if obj.get("name") == "AkPropBundle":
                    node["properties"].append([dict(f.attrib) for f in obj.findall("field")])
            banks[bank]["nodes"].append(node)
            element.clear()
        elif element.tag == "object" and element.get("name") == "BankHeader":
            banks[bank]["header"] = {f.get("name"): dict(f.attrib) for f in element.iter("field")}
        elif element.tag == "root":
            element.clear()
        stack.pop()
    return {"banks": banks, "parser_errors_or_skips": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xml', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError('Output already exists')
    graph = parse_graph(args.xml)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(graph, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'banks': len(graph['banks']), 'errors_or_skips': len(graph['parser_errors_or_skips'])}))


if __name__ == '__main__':
    main()
