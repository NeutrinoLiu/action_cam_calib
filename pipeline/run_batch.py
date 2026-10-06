#!/usr/bin/env python3
"""Calibrate every setting folder under a directory: A+B, A only and B only.

Each folder <root>/<setting>/ must hold CAL_<setting>_A.MP4 and CAL_<setting>_B.MP4. Results
land in <root>/<setting>/results/<run>/, with one calibrate.py log per run in results/.

    python pipeline/run_batch.py delivery --square-mm 20 --max-frames 200
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate.py")
STATUS = {0: "PASS", 1: "ERROR", 2: "FAIL"}   # calibrate.py exit codes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", help="folder holding one sub-folder per setting")
    ap.add_argument("--square-mm", required=True, help="MEASURED printed square size")
    ap.add_argument("--max-frames", default="200", help="frames per fit (calibrate.py default is 80)")
    ap.add_argument("--jobs", type=int, default=3, help="calibrations run in parallel")
    args = ap.parse_args()

    jobs = []
    for s in sorted(os.listdir(args.root)):
        d = os.path.join(args.root, s)
        a, b = f"CAL_{s}_A.MP4", f"CAL_{s}_B.MP4"
        if os.path.isfile(os.path.join(d, a)) and os.path.isfile(os.path.join(d, b)):
            jobs += [(d, s, [a, b]), (d, s + "_A_only", [a]), (d, s + "_B_only", [b])]
    if not jobs:
        sys.exit(f"no <setting>/CAL_<setting>_A.MP4 + _B.MP4 pairs under {args.root}")

    def run(job):
        d, name, clips = job
        t = time.time()
        os.makedirs(os.path.join(d, "results"), exist_ok=True)
        with open(os.path.join(d, "results", name + ".log"), "w") as log:
            r = subprocess.run([sys.executable, CAL, "--square-mm", args.square_mm, "--max-frames", args.max_frames,
                                "--name", name, *clips], cwd=d, stdout=log, stderr=subprocess.STDOUT)
        print(f"{name}: {STATUS.get(r.returncode, f'exit {r.returncode}')} ({time.time() - t:.0f}s)", flush=True)

    with ThreadPoolExecutor(args.jobs) as ex:
        list(ex.map(run, jobs))


if __name__ == "__main__":
    main()
