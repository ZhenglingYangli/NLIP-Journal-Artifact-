"""Convert a manually downloaded MIPO archive using the fixed integer TXT list."""
import argparse
import json
from pathlib import Path
import tarfile
import tempfile
from convert_mipo import convert

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True, help='manually downloaded authors archive')
    ap.add_argument('--output', type=Path, default=ROOT / 'benchmarks/mipo')
    a = ap.parse_args()
    manifest = ROOT / 'benchmarks/manifests/mipo_list.txt'
    names = manifest.read_text().splitlines()
    with tempfile.TemporaryDirectory(prefix='aij-mipo-') as tmp:
        archive = a.archive
        models = {}
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar.getmembers():
                if not member.isfile() or '/integer/txtfiles/' not in member.name or not member.name.endswith('.txt'):
                    continue
                source = Path(tmp) / Path(member.name).name
                name = source.stem + '.json'
                if name in models:
                    raise ValueError('duplicate input: ' + name)
                source.write_bytes(tar.extractfile(member).read())
                models[name] = convert(source)
        if len(models) != 870 or set(models) != set(names):
            raise ValueError('authors archive does not match the fixed 870-instance manifest')
        a.output.mkdir(parents=True, exist_ok=True)
        for name in names:
            target = a.output / name
            if target.exists() and json.loads(target.read_text()) != models[name]:
                raise ValueError('existing input differs from published TXT: ' + str(target))
        for name in names:
            (a.output / name).write_text(json.dumps(models[name], separators=(',', ':')) + '\n', encoding='utf-8')
    print(f'Ready: 870 exact TXT models in {a.output.resolve()}')


if __name__ == '__main__':
    main()
