#!/usr/bin/env python3
"""Install check: render the ChArUco board through a KNOWN fisheye camera (similar to the
Action 5 Pro wide lens), run calibrate.py on it, and compare recovered vs true intrinsics.

    python selftest.py          # ~2-4 minutes; prints PASS/FAIL

Exercises board detection, frame selection, fisheye fitting and all quality checks.
"""
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_board  # noqa: E402

W, H, SQ = 1920, 1080, 0.028
K_TRUE = np.array([[806.0, 0, 957.0], [0, 806.0, 548.0], [0, 0, 1]])
D_TRUE = np.array([0.19, -0.03, 0.02, -0.005])


def render(n=150, seed=0):
    rng = np.random.default_rng(seed)
    b = make_board.board(SQ)
    bw_m, bh_m = SQ * make_board.BOARD["squares_x"], SQ * make_board.BOARD["squares_y"]
    ppm = 6000 / bw_m                                           # texture pixels per metre
    tex = b.generateImage((6000, int(round(bh_m * ppm))), marginSize=0, borderBits=1)
    tex = cv2.copyMakeBorder(tex, 200, 200, 200, 200, cv2.BORDER_CONSTANT, value=255)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    pix = np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2)
    rays = cv2.fisheye.undistortPoints(pix, K_TRUE, D_TRUE.reshape(4, 1)).reshape(-1, 2)
    rays = np.hstack([rays, np.ones((len(rays), 1))])
    path = os.path.join(tempfile.mkdtemp(), "synthetic_cal.mp4")
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
    for k in range(n):
        # aim the board centre at a random pixel (corners included), 0.35-0.9 m away
        tgt = np.array([rng.uniform(0.04, 0.96) * W, rng.uniform(0.06, 0.94) * H])
        r0 = cv2.fisheye.undistortPoints(tgt.reshape(1, 1, 2), K_TRUE, D_TRUE.reshape(4, 1)).ravel()
        r0 = np.array([r0[0], r0[1], 1.0]); r0 /= np.linalg.norm(r0)
        centre = r0 * rng.uniform(0.35, 0.9)
        rv = rng.normal(0, 0.45, 3)
        R, _ = cv2.Rodrigues(rv)
        t = centre - R @ np.array([bw_m / 2, bh_m / 2, 0])
        nrm = R[:, 2]
        s = (nrm @ t) / (rays @ nrm)
        P = rays * s[:, None]
        uv = (P - t) @ R                                        # board-frame coordinates (m)
        valid = (s > 0)
        mx = (uv[:, 0] * ppm + 200).astype(np.float32); my = (uv[:, 1] * ppm + 200).astype(np.float32)
        mx[~valid] = -1; my[~valid] = -1
        # supersample: blur texture to the scale it will be sampled at
        fr = cv2.remap(tex, mx.reshape(H, W), my.reshape(H, W), cv2.INTER_AREA,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=150)
        fr = cv2.GaussianBlur(fr, (3, 3), 0.7)
        fr = np.clip(fr.astype(np.float32) * 0.8 + 25 + rng.normal(0, 2.0, fr.shape), 0, 255).astype(np.uint8)
        vw.write(cv2.cvtColor(fr, cv2.COLOR_GRAY2BGR))
    vw.release()
    return path


def main():
    print("rendering 150 synthetic board views through a known fisheye camera ...")
    clip = render()
    work = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(HERE, "calibrate.py"), "--square-mm", str(SQ * 1000),
                        "--name", "selftest", "--allow-no-metadata", clip], cwd=work)
    e = json.load(open(os.path.join(work, "results", "selftest", "intrinsics_entry.json")))
    K, D = np.array(e["K"]), np.array(e["distortion_coeffs"])
    # compare in image space: each pixel's TRUE ray, re-projected with the recovered model,
    # should land back on the same pixel (coefficients trade off; the mapping is what matters)
    ys, xs = np.mgrid[10:H - 10:20, 10:W - 10:20].astype(np.float64)
    pix = np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2)
    rays = cv2.fisheye.undistortPoints(pix, K_TRUE, D_TRUE.reshape(4, 1))
    back = cv2.fisheye.distortPoints(rays, K, D.reshape(4, 1))
    err = np.hypot(*(back - pix).reshape(-1, 2).T)
    print(f"true  f={K_TRUE[0,0]:.1f} c=({K_TRUE[0,2]:.1f},{K_TRUE[1,2]:.1f}) k={D_TRUE.tolist()}")
    print(f"found f={K[0,0]:.1f}/{K[1,1]:.1f} c=({K[0,2]:.1f},{K[1,2]:.1f}) k={np.round(D, 4).tolist()}")
    print(f"image-space error over the whole frame: median {np.median(err):.3f}px, "
          f"99th pct {np.percentile(err, 99):.3f}px, max {err.max():.3f}px")
    # tolerances typical of a good calibration: focal within 0.5 %, principal point within 2 px
    # (a sub-pixel principal-point shift is absorbed by a tiny pose rotation), 99 % of the frame
    # within 1 px in image space, and calibrate.py's own checks (held-out RMS etc.) passing
    ok = (r.returncode == 0 and abs(K[0, 0] / K_TRUE[0, 0] - 1) < 0.005
          and np.hypot(K[0, 2] - K_TRUE[0, 2], K[1, 2] - K_TRUE[1, 2]) < 2
          and np.percentile(err, 99) < 1.0)
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
