#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Rebuild every module repo's README from its files (make_module_readmes.readme: only folders that hold something,
no Drive to-do lines) and put its 3-D model section back (module_models.readme_section); remove kind-folder READMEs
that only point to Google Drive. Then commit and push each clone.

    python3 tools/regen_module_readmes.py [--dry-run] [--no-push] [M424 ...]
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modules_home, make_module_readmes as R, module_models as MM  # noqa: E402

DRIVE_ONLY = re.compile(r"(?s)^# \w+\n\n.*\n\nThe pictures are on Google Drive: see the module's README one folder up\.\n?$")
sh = lambda *a: subprocess.run(a, capture_output=True, text=True)


def main():
    dry, push = '--dry-run' in sys.argv, '--no-push' not in sys.argv
    want = {a for a in sys.argv[1:] if not a.startswith('-')}
    drive = R.load_drive()
    done = 0
    for d in modules_home.module_dirs():
        code = os.path.basename(d)
        if want and code not in want:
            continue
        real = os.path.realpath(d)
        if not os.path.isdir(real):   # merged into another module and archived
            continue
        if not dry:
            sh('git', '-C', real, 'pull', '-q', '--rebase')
        drop = []
        for k in os.listdir(real):
            f = os.path.join(real, k, 'README.md')
            if os.path.isfile(f) and DRIVE_ONLY.match(open(f, encoding='utf-8').read()):
                drop.append(os.path.join(k, 'README.md'))
        if dry:
            print(code, 'drive-only READMEs', len(drop))
            continue
        for f in drop:
            sh('git', '-C', real, 'rm', '-q', '--', f)
        R.readme(d, drive)
        mj = os.path.join(real, 'MECHANICAL', f'{code}.model.json')
        if os.path.exists(mj):
            MM.readme_section(real, json.load(open(mj)))
        sh('git', '-C', real, 'add', 'README.md')
        if sh('git', '-C', real, 'diff', '--cached', '--quiet').returncode:
            sh('git', '-C', real, 'commit', '-qm', 'README: rebuilt from the files (only folders that hold something, real file counts, '
               'no Drive to-do lines); kind READMEs that only pointed to Google Drive removed', '-m',
               'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')
            if push and sh('git', '-C', real, 'push', '-q').returncode:
                print('PUSH FAILED', code)
            done += 1
        elif push and 'ahead' in sh('git', '-C', real, 'status', '-sb').stdout.split('\n')[0]:
            sh('git', '-C', real, 'pull', '-q', '--rebase')
            if sh('git', '-C', real, 'push', '-q').returncode:
                print('PUSH FAILED', code)
    print(done, 'repos changed')


if __name__ == '__main__':
    main()
