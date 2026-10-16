"""Wwise lowercase FNV-1 candidate-name checking; a hash match needs context."""
import argparse
import json


def fnv1(text):
    value = 2166136261
    for byte in text.lower().encode('utf-8'):
        value = ((value * 16777619) & 0xffffffff) ^ byte
    return value


def branch_trie(branches):
    root = {}
    for number, branch in enumerate(branches):
        keys = [int(key['value']) for key in branch['keys']]
        node = root
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        if not keys or keys[-1] in node:
            raise ValueError('Empty/duplicate decision-tree path')
        node[keys[-1]] = ('LEAF', number, int(branch['target']['value']))
    return root


def match_branch(trie, values):
    """Conservative exact/wildcard reachability model from the original research.

    This is an analysis helper, not a proven reimplementation of all Wwise
    runtime selection policies. Null leaves do not create speech replacements.
    """
    def visit(node, depth):
        if depth >= len(values):
            return None
        key = values[depth]
        for candidate in ([key] if key != 0 else []) + [0]:
            if candidate not in node:
                continue
            child = node[candidate]
            if isinstance(child, tuple):
                if child[2] != 0:
                    return child[1]
            else:
                result = visit(child, depth + 1)
                if result is not None:
                    return result
        return None
    return visit(trie, 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='+')
    args = parser.parse_args()
    print(json.dumps({name: fnv1(name) for name in args.names}, indent=2))
