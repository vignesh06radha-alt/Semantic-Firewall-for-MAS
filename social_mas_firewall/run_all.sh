#!/bin/bash
# Full reproduction: main set x3 modes, then layer/latency ablations (firewall only, main + held-out).
PY="${PYTHON:-python}"
$PY main.py --set main --tag main_full --quiet
$PY main.py --set all --modes firewall --layers judge --tag abl_judge_only --quiet
$PY main.py --set all --modes firewall --layers detector,judge --tag abl_no_watch_no_egress --quiet
$PY main.py --set all --modes firewall --layers watch,egress --tag abl_no_semantic --quiet
$PY main.py --set all --modes firewall --sequential --tag abl_sequential --quiet
$PY main.py --set all --modes firewall --tag abl_parallel_full --quiet
echo ALL_DONE
