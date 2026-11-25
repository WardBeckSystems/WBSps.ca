#!/usr/bin/env bash
# create_module_repos.sh — make every module folder (2026/Modules/<CATEGORY>/<Mxxx>) its own GitHub repo
# WardBeckSystems/MODULES.<CATEGORY>.<Mxxx>, with a README that shows each image from the Google Drive archive,
# and put it back into WBSps.ca as a submodule. Safe to stop (Ctrl-C) and run again: finished modules are skipped.
#
#   tools/create_module_repos.sh                       every module
#   tools/create_module_repos.sh AMPLIFIERS POWER      every module in these categories
#   tools/create_module_repos.sh 2026/Modules/LOGIC/M201 ...
#
# Settings (environment):  OWNER=WardBeckSystems  VISIBILITY=public  PAUSE=30 (s between new repos)
#                          WAIT=300 (s to wait when GitHub says "too quickly")  TRIES=20
#                          NO_PARENT_COMMIT=1 (don't commit / push WBSps.ca at the end)
# Log: logs/create_module_repos.log
#
# GitHub limits how fast an account may create repos (a burst of 10-20, then a pause that can last an hour);
# the script waits and retries on its own. Needs: git, gh (logged in as an account that can create repos in OWNER),
# python3 (README via tools/make_module_readmes.py).

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${OWNER:-WardBeckSystems}"
VISIBILITY="${VISIBILITY:-public}"
PAUSE="${PAUSE:-30}"
WAIT="${WAIT:-300}"
TRIES="${TRIES:-20}"
LOG="$ROOT/logs/create_module_repos.log"
cd "$ROOT"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date +%T) $*" | tee -a "$LOG"; }

# One run at a time (two would fight over the git index).
exec 9>"$ROOT/.git/create_module_repos.lock"
flock -n 9 || { echo "Another create_module_repos.sh is running."; exit 1; }
if pgrep -f split_modules.sh >/dev/null; then
  echo "split_modules.sh (Claude's background split) is still running; stop it first."; exit 1
fi

gh auth status >/dev/null 2>&1 || { echo "gh is not logged in: run  gh auth login"; exit 1; }
gh api "orgs/$OWNER" >/dev/null 2>&1 || gh api "users/$OWNER" >/dev/null 2>&1 \
  || { echo "Can't see $OWNER on GitHub with the current gh account (gh auth switch --user $OWNER?)"; exit 1; }

# The module repos keep no media, the same rule as WBSps.ca.
GITIGNORE="$(cat <<'EOF'
# Same rules as WBSps.ca: no media (PDFs, images, video, audio), no scans, no traced vectors
*.[pP][dD][fF]
*.[pP][nN][gG]
*.[jJ][pP][gG]
*.[jJ][pP][eE][gG]
*.[jJ][pP][eE]
*.[gG][iI][fF]
*.[bB][mM][pP]
*.[tT][iI][fF]
*.[tT][iI][fF][fF]
*.[wW][eE][bB][pP]
*.[hH][eE][iI][cC]
*.[hH][eE][iI][fF]
*.[sS][vV][gG]
*.[iI][cC][oO]
*.[pP][sS][dD]
*.[aA][iI]
*.[eE][pP][sS]
*.[cC][dD][rR]
*.[rR][aA][wW]
*.[cC][rR]2
*.[nN][eE][fF]
*.[dD][nN][gG]
*.[mM][pP]4
*.[mM][oO][vV]
*.[mM]4[vV]
*.[aA][vV][iI]
*.[mM][kK][vV]
*.[wW][eE][bB][mM]
*.[wW][mM][vV]
*.[fF][lL][vV]
*.[mM][pP][gG]
*.[mM][pP][eE][gG]
*.3[gG][pP]
*.[mM][pP]3
*.[wW][aA][vV]
*.[aA][iI][fF]
*.[aA][iI][fF][fF]
*.[fF][lL][aA][cC]
*.[oO][gG][gG]
*.[mM]4[aA]
*.[aA][aA][cC]
*.[wW][mM][aA]
*.[pP][cC][tT]
*.[pP][iI][cC][tT]
*[sS][cC][aA][nN][sS]*/
[sS][cC][aA][nN]/
*(traced).dxf
*([tT][rR][aA][cC][eE][dD]).*
EOF
)"

# Which modules.
DIRS=()
if [ $# -eq 0 ]; then
  for d in 2026/Modules/*/*/; do DIRS+=("${d%/}"); done
else
  for a in "$@"; do
    a="${a%/}"
    if [ -d "2026/Modules/$a" ]; then for d in "2026/Modules/$a"/*/; do DIRS+=("${d%/}"); done
    elif [ -d "$a" ]; then DIRS+=("$a")
    else log "?? $a is not a category or module folder"; fi
  done
fi
log "== ${#DIRS[@]} modules, owner $OWNER ($VISIBILITY)"

# Create a repo, waiting out GitHub's "too quickly" limit.
create_repo() {
  local name="$1" desc="$2" out try
  gh api "repos/$OWNER/$name" >/dev/null 2>&1 && return 0
  for try in $(seq 1 "$TRIES"); do
    if out=$(gh repo create "$OWNER/$name" "--$VISIBILITY" --description "$desc" 2>&1); then
      sleep "$PAUSE"; return 0
    fi
    case "$out" in
      *"already exists"*) return 0 ;;
      *"too quickly"*|*"rate limit"*|*"secondary"*|*"abuse"*)
        log "WAIT $name: GitHub says too many new repos, try $try/$TRIES, next in ${WAIT}s"; sleep "$WAIT" ;;
      *) log "FAIL $name (create): $out"; return 1 ;;
    esac
  done
  log "FAIL $name (create): still rate limited after $TRIES tries"; return 1
}

ok=0; skip=0; fail=0
for D in "${DIRS[@]}"; do
  CAT=$(basename "$(dirname "$D")"); M=$(basename "$D")
  NAME="MODULES.$CAT.$M"; URL="https://github.com/$OWNER/$NAME.git"

  # README first: every image from the Google Drive archive.
  python3 tools/make_module_readmes.py "$D" >/dev/null || log "!! $NAME: README not written"

  if git config -f .gitmodules --get "submodule.$D.url" >/dev/null; then
    # Already a repo: just make sure its README is up to date on GitHub.
    ( cd "$D" && git add README.md .gitignore 2>/dev/null
      git diff --cached --quiet || git commit -q -m "README: every image from the Google Drive archive, each linked to the original"
      git push -q origin HEAD:main 2>&1 | grep -v '^remote:' ) || true
    log "SKIP $NAME (already a repo; README pushed)"; skip=$((skip + 1)); continue
  fi

  # Files WBSps.ca tracks in this folder (media stays out, as in WBSps.ca).
  LIST=$(mktemp)
  git ls-files -z -- "$D" | sed -z "s|^$D/||" > "$LIST"
  if [ ! -s "$LIST" ]; then log "SKIP $NAME (no tracked files)"; rm -f "$LIST"; skip=$((skip + 1)); continue; fi
  printf '.gitignore\0README.md\0' >> "$LIST"

  if ! ( cd "$D"
         [ -d .git ] || git init -q -b main
         printf '%s\n' "$GITIGNORE" > .gitignore
         git add --pathspec-from-file="$LIST" --pathspec-file-nul
         git diff --cached --quiet || git -c core.quotepath=off commit -q -m "$M ($CAT): Ward-Beck Systems module archive, split from WBSps.ca 2026/Modules"
         git rev-parse -q --verify HEAD >/dev/null ); then
    log "FAIL $NAME (local commit)"; rm -f "$LIST"; fail=$((fail + 1)); continue
  fi
  rm -f "$LIST"

  create_repo "$NAME" "Ward-Beck Systems $M ($CAT) — module archive for WBSps.ca" || { fail=$((fail + 1)); continue; }

  git -C "$D" remote get-url origin >/dev/null 2>&1 || git -C "$D" remote add origin "$URL"
  if ! git -C "$D" push -q -u origin HEAD:main 2>>"$LOG"; then log "FAIL $NAME (push)"; fail=$((fail + 1)); continue; fi

  # Hand the folder over to the submodule.
  if git rm -r -q --cached -- "$D" && git submodule add -q "$URL" "$D" >/dev/null 2>>"$LOG"; then
    log "OK   $NAME"; ok=$((ok + 1))
  else
    log "FAIL $NAME (submodule add)"; fail=$((fail + 1))
  fi
done

log "== done: $ok new, $skip skipped, $fail failed"

if [ -z "${NO_PARENT_COMMIT:-}" ]; then
  # Stage only the module submodules (new links and README commits), the .gitmodules list and these tools.
  git config -f .gitmodules --get-regexp '^submodule\.2026/Modules/.*\.path$' | awk '{print $2}' \
    | while read -r p; do git add -- "$p"; done
  git add .gitmodules tools/create_module_repos.sh tools/make_module_readmes.py
  if ! git diff --cached --quiet; then
    git commit -q -m "Modules: module folders as their own repos (MODULES.<CATEGORY>.<Mxxx>), READMEs with Drive images" \
      && git push -q && log "== WBSps.ca committed and pushed"
  fi
fi
[ "$fail" -eq 0 ]
