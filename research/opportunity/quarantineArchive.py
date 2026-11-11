"""Create a new audited archive by quarantining off-grid minute rows; never shift or fill prices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from archiveAudit import ASSETS, audit_archive


def digest(file):
    h = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def derive(archive, out):
    archive, out = Path(archive).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(archive):
        raise ValueError('derived output must be new and outside the input archive')
    raw = json.loads((archive / 'archive-validation.json').read_text())
    if raw.get('schema') != 'atlas-archive-audit-v1':
        raise ValueError('raw archive audit required')
    source = 'archive-binance-1m-quarantined-v1'
    staging = out.with_name(out.name + '.' + uuid.uuid4().hex + '.tmp')
    staging.mkdir(parents=True)
    report = {'schema': 'atlas-archive-quarantine-v1', 'recipe': 'exclude off-grid rows; no timestamp shift, price change, imputation or source splice',
              'raw_archive_sha256': digest(archive / 'archive-validation.json'), 'source': source, 'files': []}
    try:
        for asset in ASSETS:
            name = f'binance-1m/{asset}/1m.csv'
            record = next((r for r in raw['files'] if r['path'] == name), None)
            if not record or any(record.get(k) for k in ('invalid_rows', 'duplicate_or_reversed', 'invalid_taker_volume', 'changed_during_audit')):
                raise ValueError('raw minute defects require a separate explicit recipe')
            original = archive / 'history' / name
            if digest(original) != record['sha256']:
                raise ValueError('raw input hash changed')
            target = staging / 'history' / source / asset / '1m.csv'
            rejected = staging / 'quarantine' / asset / 'off-grid.csv'
            target.parent.mkdir(parents=True); rejected.parent.mkdir(parents=True)
            kept, dropped = 0, 0
            with original.open('rb') as reader, target.open('xb') as writer, rejected.open('xb') as bad:
                header = reader.readline(); writer.write(header); bad.write(header)
                for line in reader:
                    if not line.strip():
                        continue
                    ts = int(line.split(b',', 1)[0])
                    if ts % 60000:
                        bad.write(line); dropped += 1
                    else:
                        writer.write(line); kept += 1
            if dropped != record['misaligned'] or kept + dropped != record['rows'] or digest(original) != record['sha256']:
                raise ValueError('quarantine counts/input changed')
            report['files'].append({'asset': asset, 'input_sha256': record['sha256'], 'kept': kept, 'quarantined': dropped,
                                    'output_sha256': digest(target), 'quarantine_sha256': digest(rejected)})
        for namespace in ('tradingview', 'yahoo', 'binance-funding'):
            src = archive / 'history' / namespace
            if src.is_dir():
                shutil.copytree(src, staging / 'history' / namespace)
        audit = audit_archive(staging / 'history', source=source)
        if not audit['ready']:
            raise ValueError('derived minute audit failed')
        (staging / 'archive-validation.json').write_text(json.dumps(audit, indent=2) + '\n')
        (staging / 'derivation.json').write_text(json.dumps(report, indent=2) + '\n')
        if out.exists():
            raise ValueError('output appeared during derivation')
        os.rename(staging, out)
        return report
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive'); parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(derive(args.archive, args.out), indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
