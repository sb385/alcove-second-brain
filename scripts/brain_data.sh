#!/usr/bin/env bash
# Persistent data (Excel, Wispr uploads, run archive) lives on its own branch,
# checked out as a worktree at .brain-data. Code stays on main.
#   scripts/brain_data.sh pull            # create/update the worktree
#   scripts/brain_data.sh push "message"  # commit data/ and push
# Then run the app with DATA_DIR=.brain-data/data
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
BR=claude/brain-data
WT=.brain-data

case "${1:-}" in
  pull)
    if [ ! -d "$WT/.git" ] && [ ! -f "$WT/.git" ]; then
      if git fetch origin "$BR" 2>/dev/null; then
        git worktree add -B "$BR" "$WT" "origin/$BR"
      else
        echo "brain-data branch not found; creating it"
        git worktree add --detach "$WT"
        git -C "$WT" checkout --orphan "$BR"
        git -C "$WT" rm -rf --quiet . || true
      fi
    else
      git -C "$WT" pull --rebase origin "$BR" || true
    fi
    mkdir -p "$WT/data"
    ;;
  push)
    git -C "$WT" add -A data
    if git -C "$WT" diff --cached --quiet; then echo "no data changes"; exit 0; fi
    git -C "$WT" commit -q -m "${2:-brain data update}"
    for i in 1 2 3; do
      git -C "$WT" pull --rebase origin "$BR" 2>/dev/null || true
      if git -C "$WT" push -u origin "$BR"; then exit 0; fi
      sleep 5
    done
    echo "push failed" >&2; exit 1
    ;;
  *) echo "usage: $0 pull|push [message]" >&2; exit 2 ;;
esac
