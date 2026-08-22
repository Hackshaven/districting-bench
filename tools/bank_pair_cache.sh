#!/usr/bin/env bash
# Commit and push the Experiment 2 pair cache as it fills.
#
# The cache makes a killed analysis resumable, but only if it outlives the
# container -- and a gitignored directory does not. This project lost twelve
# sampling checkpoints that way before, and then lost the same analysis four
# times because its cache had the identical hole. See docs/RESEARCH-LOOP-PLAYBOOK.md
# part 1: the only durable thing is a pushed commit; everything else is a cache.
#
# Usage: tools/bank_pair_cache.sh [interval_seconds]
set -u
cd "$(dirname "$0")/.."
interval="${1:-180}"
last=0
while pgrep -f experiment_2_tradeoffs >/dev/null; do
  n=$(find docs/experiment-2/pair-cache -name '*.json' 2>/dev/null | wc -l)
  if [ "$n" -gt "$last" ]; then
    git add docs/experiment-2/pair-cache 2>/dev/null
    if ! git diff --cached --quiet 2>/dev/null; then
      git commit -q -m "Bank $n cached pair results from the Experiment 2 re-derivation

Progress banked mid-run so a container reclaim costs the pairs still in
flight rather than the whole analysis. This analysis has now been
destroyed four times; the cache that was meant to prevent it was itself
gitignored, which is the same hole that lost twelve sampling checkpoints
earlier.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01S1zrECPnQPY8LARrLDuXmx" 2>/dev/null
      for attempt in 1 2 3 4; do
        git push -q origin claude/repo-initialization-rci3fb 2>/dev/null && break
        sleep $((2 ** attempt))
      done
      echo "banked $n pairs at $(date +%H:%M)"
    fi
    last=$n
  fi
  sleep "$interval"
done
echo "run finished; final bank at $(date +%H:%M)"
git add docs/experiment-2/pair-cache docs/experiment-2/*.json 2>/dev/null
git diff --cached --quiet 2>/dev/null || git commit -q -m "Final pair cache and results from the Experiment 2 re-derivation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01S1zrECPnQPY8LARrLDuXmx"
git push -q origin claude/repo-initialization-rci3fb 2>/dev/null
