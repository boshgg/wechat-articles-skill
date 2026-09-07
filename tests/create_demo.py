import argparse
import json
from pathlib import Path
from fixtures import create_fixture

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
manifest = create_fixture(args.out.resolve())
print(manifest)
print(json.dumps(json.loads(manifest.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
