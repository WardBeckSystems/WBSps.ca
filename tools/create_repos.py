#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Create the queued WardBeckSystems repos on GitHub and push their local folders, one at a time.

    python3 tools/create_repos.py [--dry-run]

The queue is tools/repo_queue.json: [{"name", "path" (local folder with its own git), "visibility" ("public" /
"private"), "description"}]. GitHub limits repo creation ("too many repositories, too quickly"): on that answer
it waits 3 minutes and tries again, never gives up. A repo that exists already is only pushed. Done entries are
marked "done": true in the queue, so a rerun carries on where it stopped.
"""
import json, os, subprocess, sys, time

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(TOP, 'tools', 'repo_queue.json')
OWNER = 'WardBeckSystems'
sh = lambda *a, **k: subprocess.run(a, capture_output=True, text=True, **k)


def main():
    dry = '--dry-run' in sys.argv
    seen = set()
    while True:   # entries added to the queue while this runs are taken too
        todo = [e for e in json.load(open(Q)) if not e.get('done') and e['name'] not in seen]
        if not todo:
            break
        e = todo[0]
        seen.add(e['name'])
        name, path = e['name'], os.path.join(TOP, e['path'])
        print(f'{name}: {e.get("visibility", "public")}', flush=True)
        if dry:
            continue
        if sh('gh', 'repo', 'view', f'{OWNER}/{name}').returncode:
            while True:
                r = sh('gh', 'repo', 'create', f'{OWNER}/{name}', '--' + e.get('visibility', 'public'),
                       '--description', e.get('description', '')[:300])
                if not r.returncode or not sh('gh', 'repo', 'view', f'{OWNER}/{name}').returncode:
                    break
                print(f'  create failed ({r.stderr.strip()[:80]}); waiting 3 min', flush=True)
                time.sleep(180)
            time.sleep(20)
        url = f'https://github.com/{OWNER}/{name}.git'
        if sh('git', '-C', path, 'remote', 'get-url', 'origin').returncode:
            sh('git', '-C', path, 'remote', 'add', 'origin', url)
        r = sh('git', '-C', path, 'push', '-q', '-u', 'origin', 'HEAD:main')
        if r.returncode:
            print(f'  push failed: {r.stderr.strip()[:300]}', flush=True)
            continue
        fresh = json.load(open(Q))   # the queue may have grown while this ran: mark this one done in the file as it is now
        for f in fresh:
            if f['name'] == name:
                f['done'] = True
        json.dump(fresh, open(Q, 'w'), indent=1)
        print('  pushed', flush=True)


if __name__ == '__main__':
    main()
