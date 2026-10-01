#!/usr/bin/env python3
"""Fingerprinted cache for locally generated ROM-derived assets."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

SCHEMA = 1

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def sha1_file(path: Path) -> str:
    h=hashlib.sha1()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def fingerprint(*values, files=()):
    h=hashlib.sha256()
    for value in values:
        data=str(value).encode()
        h.update(len(data).to_bytes(8,"big")); h.update(data)
    for path in files:
        path=Path(path).resolve()
        data=str(path).encode()
        h.update(len(data).to_bytes(8,"big")); h.update(data)
        h.update(bytes.fromhex(sha256_file(path)))
    return h.hexdigest()

class AssetCache:
    def __init__(self, root: Path):
        self.root=Path(root).expanduser().resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/".asset-cache.json"
        self.state={"schema":SCHEMA,"entries":{}}
        if self.path.is_file():
            try: loaded=json.loads(self.path.read_text())
            except (OSError,json.JSONDecodeError): loaded=None
            if isinstance(loaded,dict) and loaded.get("schema")==SCHEMA: self.state=loaded

    def is_fresh(self,key,expected,outputs):
        record=self.state.get("entries",{}).get(key)
        return bool(isinstance(record,dict) and record.get("fingerprint")==expected
                    and all(Path(p).is_file() for p in outputs))

    def mark(self,key,expected,outputs):
        self.state.setdefault("entries",{})[key]={
            "fingerprint":expected,
            "outputs":[str(Path(p).resolve()) for p in outputs],
        }
        self.path.write_text(json.dumps(self.state,indent=2)+"\n")
