#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Build, test and deploy every module plugin, then prove REAPER boots and loads each one.

For every 2026/Modules/<CAT>/<M> (links to the clones)/SOFTWARE/plugin crate:
  1. cargo test --no-default-features          the DSP's own tests
  2. cargo xtask bundle <crate> --release       target/bundled/<crate>.vst3 and .clap
  3. deploy                                     the VST3 into ~/.vst3 and the CLAP into ~/.clap, the folders on
                                                REAPER's plug-in path (reaper.ini vstpath)
  4. REAPER                                     REAPER starts (-nosplash, on an empty test project of its own), runs a ReaScript that puts
                                                every plugin on a track as VST3 and as CLAP, checks each loaded
                                                with its parameters, writes the result and quits. A REAPER that
                                                does not boot, or a plugin that does not load, fails the run.

    python3 tools/build_plugins.py                  # everything
    python3 tools/build_plugins.py M464 M404        # some modules
    python3 tools/build_plugins.py --no-build       # deploy what is built and test it in REAPER
    python3 tools/build_plugins.py --no-reaper      # build and deploy only
    python3 tools/build_plugins.py --update-core    # cargo update -p wbs-panel first (new Plugin-Core)

Exit status 0 only when every step passed.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modules_home  # noqa: E402  the module folders (2026/Modules/<CAT>/<M> -> clones)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'Ward-Beck-Plugin-Core')
SHIMS = os.path.join(CORE, 'build-shims', 'linux')
HOME = os.path.expanduser('~')
VST3_DIR = os.path.join(HOME, '.vst3')
CLAP_DIR = os.path.join(HOME, '.clap')
REAPER = next((p for p in (os.path.join(HOME, 'opt', 'REAPER', 'reaper'), '/opt/REAPER/reaper', '/usr/local/bin/reaper',
                           '/usr/bin/reaper') if os.path.exists(p)), None)
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
FLAGS = {a for a in sys.argv[1:] if a.startswith('--')}


def crates():
    out = []
    for toml in sorted(os.path.join(m, 'SOFTWARE', 'plugin', 'Cargo.toml') for m in modules_home.module_dirs()
                       if os.path.exists(os.path.join(m, 'SOFTWARE', 'plugin', 'Cargo.toml'))):
        d = os.path.dirname(toml)
        code = d.split(os.sep)[-3]
        if ARGS and code not in ARGS:
            continue
        name = re.search(r'^name = "([^"]+)"', open(toml).read(), re.M).group(1)
        lib = open(os.path.join(d, 'src', 'lib.rs')).read()
        title = re.search(r'const NAME: &\'static str = "([^"]+)"', lib).group(1)
        out.append({'code': code, 'dir': d, 'crate': name, 'title': title})
    return out


def env():
    e = dict(os.environ)
    lib = os.path.join(SHIMS, 'lib')
    if not os.path.isdir(lib) and os.path.exists(os.path.join(SHIMS, 'links.sh')):
        subprocess.run(['sh', os.path.join(SHIMS, 'links.sh')], check=False)
    e['PKG_CONFIG_PATH'] = SHIMS + (':' + e['PKG_CONFIG_PATH'] if e.get('PKG_CONFIG_PATH') else '')
    e['LIBRARY_PATH'] = lib + (':' + e['LIBRARY_PATH'] if e.get('LIBRARY_PATH') else '')
    return e


def run(cmd, cwd, e):
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-25:])
    return r.returncode == 0, tail


def build(c, e):
    if '--update-core' in FLAGS:
        run(['cargo', 'update', '-p', 'wbs-panel'], c['dir'], e)
    ok, log = run(['cargo', 'test', '--no-default-features', '--quiet'], c['dir'], e)
    passed = sum(int(n) for n in re.findall(r'test result: ok\. (\d+) passed', log))
    if not ok:
        return f'tests failed\n{log}'
    c['tests'] = passed
    ok, log = run(['cargo', 'xtask', 'bundle', c['crate'], '--release'], c['dir'], e)
    if not ok:
        return f'bundle failed\n{log}'
    return None


def deploy(c):
    b = os.path.join(c['dir'], 'target', 'bundled')
    vst3, clap = os.path.join(b, c['crate'] + '.vst3'), os.path.join(b, c['crate'] + '.clap')
    if not (os.path.isdir(vst3) and os.path.exists(clap)):
        return 'not built'
    os.makedirs(VST3_DIR, exist_ok=True)
    os.makedirs(CLAP_DIR, exist_ok=True)
    dst = os.path.join(VST3_DIR, os.path.basename(vst3))
    if os.path.lexists(dst):
        shutil.rmtree(dst) if os.path.isdir(dst) and not os.path.islink(dst) else os.remove(dst)
    shutil.copytree(vst3, dst)
    shutil.copy2(clap, os.path.join(CLAP_DIR, os.path.basename(clap)))
    c['deployed'] = [dst, os.path.join(CLAP_DIR, os.path.basename(clap))]
    return None


LUA = r'''
local out = io.open(os.getenv("WBS_OUT"), "w")
out:write("BOOT ", reaper.GetAppVersion(), "\n")
reaper.InsertTrackAtIndex(0, false)
local tr = reaper.GetTrack(0, 0)
for line in io.lines(os.getenv("WBS_LIST")) do
  local i = reaper.TrackFX_AddByName(tr, line, false, -1)
  if i < 0 then
    out:write("FAIL\t", line, "\tnot found\n")
  else
    local _, name = reaper.TrackFX_GetFXName(tr, i, "")
    local np = reaper.TrackFX_GetNumParams(tr, i)
    out:write((np > 0) and "OK" or "FAIL", "\t", line, "\t", name, " (", np, " parameters)\n")
  end
end
out:write("END\n")
out:close()
-- the test's own project file: saving it leaves nothing unsaved, so REAPER quits without asking
reaper.Main_SaveProject(0, false)
reaper.Main_OnCommand(40004, 0) -- File: Quit
'''


def reaper_test(cs):
    if not REAPER:
        return {'boot': False, 'why': 'REAPER not found'}
    if subprocess.run(['pgrep', '-x', 'reaper'], capture_output=True).returncode == 0:
        return {'boot': False, 'why': 'REAPER is already running: close it and run again'}
    tmp = tempfile.mkdtemp(prefix='wbs_reaper_')
    lua, lst, out, rpp = (os.path.join(tmp, n) for n in ('probe.lua', 'list.txt', 'out.txt', 'test.RPP'))
    open(lua, 'w').write(LUA)
    open(rpp, 'w').write('<REAPER_PROJECT 0.1 "7.0" 0\n>\n')
    with open(lst, 'w') as fh:
        for c in cs:
            fh.write(f'VST3:{c["title"]}\nCLAP:{c["title"]}\n')
    e = dict(os.environ, WBS_OUT=out, WBS_LIST=lst)
    t0 = time.time()
    proc = subprocess.Popen([REAPER, '-nosplash', rpp, lua], env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    why, quit_s = None, None

    def done():
        return os.path.exists(out) and 'END' in open(out).read()
    while proc.poll() is None and not done() and time.time() - t0 < 240:
        time.sleep(0.5)
    if not done() and proc.poll() is None:
        why = 'REAPER did not finish loading the plugins within 240 s (hung?)'
    t1 = time.time()
    try:
        proc.wait(timeout=45)          # REAPER quits by itself after the test
        quit_s = round(time.time() - t1, 1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    res = {'boot': False, 'why': why, 'secs': round(t1 - t0, 1), 'quit': quit_s, 'lines': []}
    if os.path.exists(out):
        text = open(out).read()
        res['boot'] = text.startswith('BOOT ')
        res['version'] = text.splitlines()[0][5:] if res['boot'] else ''
        res['lines'] = [l.split('\t') for l in text.splitlines() if l.startswith(('OK', 'FAIL'))]
        res['complete'] = 'END' in text
    elif not why:
        res['why'] = 'REAPER exited without running the test script'
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def main():
    cs = crates()
    if not cs:
        sys.exit('no plugin crates matched')
    e = env()
    bad = 0
    for c in cs:
        if '--no-build' not in FLAGS:
            print(f'build  {c["code"]:7} {c["crate"]} …', flush=True)
            err = build(c, e)
            if err:
                print(f'  FAIL {err}')
                bad += 1
                continue
            print(f'  ok   {c.get("tests", 0)} tests, VST3 + CLAP bundled')
        err = deploy(c)
        if err:
            print(f'  FAIL deploy: {err}')
            bad += 1
        else:
            print(f'  deployed to {VST3_DIR} and {CLAP_DIR}')
    if '--no-reaper' not in FLAGS:
        live = [c for c in cs if c.get('deployed')]
        print(f'\nREAPER: boot and load {len(live)} plugins × VST3 / CLAP …', flush=True)
        r = reaper_test(live)
        if not r['boot']:
            print(f'  FAIL REAPER did not boot: {r.get("why")}')
            bad += 1
        else:
            q = f'quit {r["quit"]} s later' if r['quit'] is not None else 'did NOT quit within 45 s (a dialog?): closed it'
            print(f'  REAPER {r["version"]} booted and loaded the plugins in {r["secs"]} s; {q}')
            for st, what, *rest in r['lines']:
                print(f'  {st:4} {what:48} {rest[0] if rest else ""}')
                bad += st != 'OK'
            if not r.get('complete') or len(r['lines']) != 2 * len(live):
                print('  FAIL the test script did not finish')
                bad += 1
    print('\nALL PASSED' if not bad else f'\n{bad} FAILED')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
