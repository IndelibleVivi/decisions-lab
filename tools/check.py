"""One offline validation entry for local development and CI."""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-only', action='store_true', help='stdlib CLI/data checks; skip static site and JavaScript checks')
    args = parser.parse_args()
    commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                [sys.executable, '-m', 'decision_lab', 'validate', 'experiments/next-action/cases.json']]
    if not args.core_only:
        node = shutil.which('node')
        if not node:
            parser.error('Full checks require Node.js 22+; CLI/data checks can use --core-only.')
        commands += [[node, 'tests/reader_behavior.test.js'], [node, 'tests/evidence_behavior.test.js'],
                     [node, 'tests/visual_behavior.test.js'], [node, 'tests/atlas_behavior.test.js'], [node, '--check', 'site/lab.js'],
                     [sys.executable, 'tools/build_site.py'], [sys.executable, 'tools/check_site.py']]
    for command in commands:
        print('+ ' + ' '.join(command[1:]), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print('Offline checks passed. No provider calls or deployment performed.')

if __name__ == '__main__':
    try: main()
    except subprocess.CalledProcessError as exc: sys.exit(exc.returncode)
