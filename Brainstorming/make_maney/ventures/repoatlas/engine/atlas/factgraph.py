"""The Codebase Fact Graph: verified facts with evidence, in diffable snapshots.

Every fact: {id, kind, data, evidence, source, verified}. Evidence is a list
of {"path": ..., "line": ...} pointing into the scanned repo. Facts carry no
timestamps (snapshot metadata does), so identical code yields identical
snapshots and diffs are pure signal.
"""

import hashlib
import json
import os


class FactGraph:
    def __init__(self, repo_name=""):
        self.repo_name = repo_name
        self.facts = []

    def add(self, kind, data, evidence=None, source="", verified=False):
        fact = {
            "id": f"F{len(self.facts) + 1:05d}",
            "kind": kind,
            "data": data,
            "evidence": evidence or [],
            "source": source,
            "verified": bool(verified),
        }
        self.facts.append(fact)
        return fact["id"]

    def query(self, kind=None, **filters):
        out = []
        for fact in self.facts:
            if kind is not None and fact["kind"] != kind:
                continue
            if any(fact["data"].get(k) != v for k, v in filters.items()):
                continue
            out.append(fact)
        return out

    @staticmethod
    def fingerprint(fact):
        payload = json.dumps([fact["kind"], fact["data"]], sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def diff(self, older):
        """Compare against an older graph. Returns added/removed fact lists."""
        mine = {self.fingerprint(f): f for f in self.facts}
        theirs = {self.fingerprint(f): f for f in older.facts}
        added = [mine[fp] for fp in mine.keys() - theirs.keys()]
        removed = [theirs[fp] for fp in theirs.keys() - mine.keys()]
        key = lambda f: (f["kind"], json.dumps(f["data"], sort_keys=True))
        return {"added": sorted(added, key=key), "removed": sorted(removed, key=key)}

    def save(self, path, meta=None):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "repo": self.repo_name,
                "meta": meta or {},
                "facts": self.facts,
            }, fh, indent=1)

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        graph = cls(data.get("repo", ""))
        graph.facts = data["facts"]
        return graph
