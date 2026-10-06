#!/usr/bin/env python3
"""Calibrate one DJI Osmo Action 5 Pro setting from ChArUco board videos (OpenCV fisheye model).

All input clips must be recorded with the SAME settings (lens mode, resolution, fps,
stabilization); the script checks this from the camera metadata and refuses to mix.

Usage:
    python calibrate.py --square-mm 28.0 --name wide_4k_30_rocksteady CAL_*.MP4

Writes to results/<name>/:
    intrinsics_entry.json   K, fisheye k1..k4, settings, quality numbers
    coverage.png            where board corners landed in the frame (aim: everywhere)
    report.txt              the PASS/FAIL checks below, human readable

Checks (thresholds scale with image width; numbers below are for 1920 px wide):
    held-out reprojection RMS   <= 0.5 px  (frames never used for fitting)
    frame coverage              >= 80 % of a 12x8 grid, and all four corner regions hit
    model valid to the corners  distortion curve still increasing at the farthest corner
    frames used                 >= 30

Requires: numpy, opencv-contrib-python (>= 4.7, for cv2.aruco.CharucoDetector),
ffmpeg/ffprobe on PATH (to read the settings).
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_board  # noqa: E402
import read_settings  # noqa: E402

GRID = (12, 8)          # coverage grid (cols, rows)
MIN_CORNERS = 12        # ChArUco corners needed for a frame to count


def detect(paths, board, step_target=900):
    """Yield (gray-shape, corners Nx2, ids N) for frames where the board is found."""
    det = cv2.aruco.CharucoDetector(board)
    found, size = [], None
    for p in paths:
        cap = cv2.VideoCapture(p)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, n * len(paths) // step_target)
        i = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
                    size = g.shape[::-1]
                    cc, ids, _, _ = det.detectBoard(g)
                    if ids is not None and len(ids) >= MIN_CORNERS:
                        x, y, w, h = cv2.boundingRect(cc.astype(np.float32))
                        sharp = cv2.Laplacian(g[y:y + h, x:x + w], cv2.CV_64F).var()
                        found.append(dict(src=p, frame=i, pts=cc.reshape(-1, 2).astype(np.float64),
                                          ids=ids.ravel(), sharp=sharp))
            i += 1
        cap.release()
    return found, size


def select(frames, size, max_frames):
    """Greedy: prefer frames that add uncovered grid cells; drop the blurriest third first."""
    if not frames:
        return []
    cut = np.percentile([f["sharp"] for f in frames], 33)
    pool = [f for f in frames if f["sharp"] >= cut] or frames
    W, H = size
    for f in pool:
        cx = np.clip((f["pts"][:, 0] / W * GRID[0]).astype(int), 0, GRID[0] - 1)
        cy = np.clip((f["pts"][:, 1] / H * GRID[1]).astype(int), 0, GRID[1] - 1)
        f["cells"] = set(zip(cx.tolist(), cy.tolist()))
    chosen, covered = [], {}
    while pool and len(chosen) < max_frames:
        # value = cells seen fewer than 3 times so far, plus a little for corner count
        best = max(pool, key=lambda f: sum(1 for c in f["cells"] if covered.get(c, 0) < 3) + len(f["ids"]) / 200)
        pool.remove(best)
        chosen.append(best)
        for c in best["cells"]:
            covered[c] = covered.get(c, 0) + 1
    return chosen


def _fisheye_flag(name):
    """OpenCV 4 keeps fisheye flags in cv2.fisheye (with fisheye-specific values);
    OpenCV 5 moved them to the cv2 namespace."""
    v = getattr(cv2.fisheye, name, None)
    return v if v is not None else getattr(cv2, name)


def obj_img(frames, board):
    allc = board.getChessboardCorners()
    # (1, N, 3) / (1, N, 2): the shape both OpenCV 4 and OpenCV 5 fisheye.calibrate accept
    obj = [allc[f["ids"]].reshape(1, -1, 3).astype(np.float64) for f in frames]
    img = [f["pts"].reshape(1, -1, 2).astype(np.float64) for f in frames]
    return obj, img


def fit(frames, board, size):
    W, H = size
    obj, img = obj_img(frames, board)
    K = np.array([[0.42 * W, 0, W / 2], [0, 0.42 * W, H / 2], [0, 0, 1]], float)
    D = np.zeros((4, 1))
    flags = (_fisheye_flag("CALIB_RECOMPUTE_EXTRINSIC") | _fisheye_flag("CALIB_FIX_SKEW")
             | _fisheye_flag("CALIB_USE_INTRINSIC_GUESS"))
    crit = (cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 200, 1e-9)
    try:
        rms, K, D, rv, tv = cv2.fisheye.calibrate(obj, img, size, K.copy(), D.copy(), flags=flags, criteria=crit)
    except cv2.error:
        rms, K, D, rv, tv = fit_lm(obj, img, K, D)
    per = []
    for o, i, r, t in zip(obj, img, rv, tv):
        pr, _ = cv2.fisheye.projectPoints(o, r, t, K, D)
        per.append(np.sqrt(np.mean(np.sum((pr - i) ** 2, axis=2))))
    return rms, K, D, np.array(per)


def fit_lm(obj, img, K, D, iters=300):
    """Levenberg-Marquardt fallback for when cv2.fisheye.calibrate aborts.

    cv2.fisheye.calibrate re-initialises every frame's pose from undistorted points on each
    iteration. With wide lenses an intermediate distortion estimate can stop being invertible
    near the frame edge, and the call aborts (InitExtrinsics: fabs(norm_u1) > 0). This minimises
    the same reprojection error but only uses the forward projection, which is always defined.
    Parameters: fx, fy, cx, cy, k1..k4 (skew fixed at 0) plus one rvec/tvec per frame.
    """
    def unpack(p):
        return np.array([[p[0], 0, p[2]], [0, p[1], p[3]], [0, 0, 1]]), p[4:8].reshape(4, 1)

    def project(intr, poses, jac):
        Kp, Dp = unpack(intr)
        out = []
        for o, i, ps in zip(obj, img, poses):
            pr, J = cv2.fisheye.projectPoints(o, ps[:3].reshape(3, 1), ps[3:].reshape(3, 1), Kp, Dp)
            r = (pr - i).reshape(-1)
            out.append((r, J[:, :8], J[:, 8:14]) if jac else r)
        return out

    poses = []
    for o, i in zip(obj, img):                      # start poses from the initial K, D
        und = cv2.fisheye.undistortPoints(i, K, D)
        _, r, t = cv2.solvePnP(o.reshape(-1, 3), und.reshape(-1, 2), np.eye(3), None)
        poses.append(np.concatenate([r.ravel(), t.ravel()]))
    poses = np.array(poses)
    intr = np.array([K[0, 0], K[1, 1], K[0, 2], K[1, 2], *D.ravel()], float)
    cost = sum(r @ r for r in project(intr, poses, False))
    lam = 1e-3
    for _ in range(iters):
        blocks = project(intr, poses, True)
        U = sum(A.T @ A for _, A, _ in blocks)
        ga = sum(A.T @ r for r, A, _ in blocks)
        while lam < 1e10:
            S, rhs, Vinv = U + lam * np.diag(np.diag(U)), ga.copy(), []
            for r, A, B in blocks:                  # Schur complement: eliminate the per-frame poses
                V = B.T @ B
                Vi = np.linalg.inv(V + lam * np.diag(np.diag(V)))
                W = A.T @ B
                S -= W @ Vi @ W.T
                rhs -= W @ Vi @ (B.T @ r)
                Vinv.append((Vi, W, B.T @ r))
            da = -np.linalg.solve(S, rhs)
            new_poses = poses + np.array([-(Vi @ (gb + W.T @ da)) for Vi, W, gb in Vinv])
            new_cost = sum(r @ r for r in project(intr + da, new_poses, False))
            if np.isfinite(new_cost) and new_cost < cost:
                break
            lam *= 5
        else:
            break                                   # no step reduces the error any more
        done = cost - new_cost < 1e-12 * cost
        intr, poses, cost, lam = intr + da, new_poses, new_cost, max(lam / 3, 1e-12)
        if done:
            break
    K, D = unpack(intr)
    n = sum(o.shape[1] for o in obj)
    return np.sqrt(cost / n), K, D, [p[:3].reshape(3, 1) for p in poses], [p[3:].reshape(3, 1) for p in poses]


def fit_robust(frames, board, size, log):
    """Fit, then repeatedly drop the worst frame while it is an outlier (<= 15 % of frames)."""
    frames = list(frames)
    for _ in range(max(1, int(0.15 * len(frames)))):
        try:
            rms, K, D, per = fit(frames, board, size)
        except cv2.error as e:
            log(f"  fit failed ({str(e).splitlines()[-1][:80]}); dropping one frame and retrying")
            frames.pop(int(np.argmin([len(f["ids"]) for f in frames])))
            continue
        worst = int(np.argmax(per))
        if per[worst] > max(3 * np.median(per), 1.0 * size[0] / 1920):
            log(f"  dropping outlier frame {frames[worst]['src']}#{frames[worst]['frame']} "
                f"(rms {per[worst]:.2f}px)")
            frames.pop(worst)
            continue
        return rms, K, D, per, frames
    rms, K, D, per = fit(frames, board, size)
    return rms, K, D, per, frames


def holdout_rms(frames, board, K, D):
    obj, img = obj_img(frames, board)
    errs = []
    for o, i in zip(obj, img):
        und = cv2.fisheye.undistortPoints(i, K, D).reshape(-1, 2)  # normalised pinhole coords
        # Initial pose from points within 60 deg of the axis: OpenCV returns -1e6 for points its
        # iterative undistortion fails on, and points near 90 deg get huge pinhole coordinates
        # that swamp PnP (both seen near the edge of wide frames). Then refine the pose in pixel
        # space with every point, which is what is scored.
        good = np.hypot(und[:, 0], und[:, 1]) < np.tan(np.radians(60))
        if good.sum() < 6:
            good = np.all(np.abs(und) < 1e5, axis=1)
        if good.sum() < 6:
            continue
        ok, r, t = cv2.solvePnP(o.reshape(-1, 3)[good], und[good], np.eye(3), None,
                                flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            continue
        r, t = refine_pose(o, i, r, t, K, D)
        pr, _ = cv2.fisheye.projectPoints(o, r, t, K, D)
        errs.append(np.sum((pr - i) ** 2, axis=2).ravel())
    return float(np.sqrt(np.mean(np.concatenate(errs)))) if errs else float("nan")


def refine_pose(o, i, r, t, K, D, iters=30):
    """Levenberg-Marquardt on one frame's pose (K, D fixed), minimising pixel reprojection error."""
    def project(p):
        pr, J = cv2.fisheye.projectPoints(o, p[:3].reshape(3, 1), p[3:].reshape(3, 1), K, D)
        return (pr - i).reshape(-1), J[:, 8:14]

    p = np.concatenate([np.ravel(r), np.ravel(t)]).astype(float)
    e, J = project(p)
    cost, lam = e @ e, 1e-3
    for _ in range(iters):
        H, g = J.T @ J, J.T @ e
        while lam < 1e10:
            q = p - np.linalg.solve(H + lam * np.diag(np.diag(H)), g)
            e2, J2 = project(q)
            if np.isfinite(e2 @ e2) and e2 @ e2 < cost:
                break
            lam *= 5
        else:
            break
        done = cost - e2 @ e2 < 1e-12 * cost
        p, e, J, cost, lam = q, e2, J2, e2 @ e2, lam / 3
        if done:
            break
    return p[:3].reshape(3, 1), p[3:].reshape(3, 1)


def valid_to_corners(K, D, size):
    """Is r_d = f * theta_d(theta) still increasing when it reaches the farthest corner?"""
    W, H = size
    f = (K[0, 0] + K[1, 1]) / 2
    corner = max(np.hypot(x - K[0, 2], y - K[1, 2]) for x in (0, W) for y in (0, H))
    th = np.linspace(0, np.pi / 2 * 1.4, 20001)
    k = D.ravel()
    td = th * (1 + k[0] * th ** 2 + k[1] * th ** 4 + k[2] * th ** 6 + k[3] * th ** 8)
    rd = f * td
    inc = np.diff(rd) > 0
    reach = rd[np.argmin(inc)] if not inc.all() else rd[-1]
    return bool(reach >= corner), float(reach), float(corner)


def lambda_equiv(K, D, size):
    """Same 1-parameter radial measure used in the footage audit (comparable numbers):
    p_u = c + (p_d - c)(1 + lam |p_d - c|^2 / R^2), c = image centre, R = 1000 * W/1920,
    fitted over distorted radii <= 800 * W/1920."""
    W, H = size
    s = W / 1920
    ys, xs = np.mgrid[-0.3 * H:1.3 * H:H / 60, -0.3 * W:1.3 * W:W / 90]
    pu = np.stack([xs.ravel(), ys.ravel()], 1)
    n = (pu - K[:2, 2]) / np.diag(K)[:2]
    pd = cv2.fisheye.distortPoints(n.reshape(-1, 1, 2), K, D).reshape(-1, 2)
    c = np.array([W / 2, H / 2])
    ok = (np.hypot(*(pd - c).T) <= 800 * s) & np.isfinite(pd).all(1)
    pu, pd = pu[ok], pd[ok]
    d = pd - c
    r2 = (d ** 2).sum(1) / (1000 * s) ** 2
    A = (d * r2[:, None]).ravel()
    return float(A @ (pu - c - d).ravel() / (A @ A))


def coverage(frames, size, out_png):
    W, H = size
    canvas = np.full((H // 2, W // 2, 3), 255, np.uint8)
    hits = np.zeros(GRID[::-1], int)
    for f in frames:
        for x, y in f["pts"]:
            cv2.circle(canvas, (int(x / 2), int(y / 2)), 2, (40, 90, 200), -1)
            hits[min(int(y / H * GRID[1]), GRID[1] - 1), min(int(x / W * GRID[0]), GRID[0] - 1)] += 1
    for gx in range(1, GRID[0]):
        cv2.line(canvas, (gx * W // 2 // GRID[0], 0), (gx * W // 2 // GRID[0], H // 2), (200, 200, 200), 1)
    for gy in range(1, GRID[1]):
        cv2.line(canvas, (0, gy * H // 2 // GRID[1]), (W // 2, gy * H // 2 // GRID[1]), (200, 200, 200), 1)
    cv2.imwrite(out_png, canvas)
    frac = float((hits > 0).mean())
    corners = [hits[:2, :3].sum() > 0, hits[:2, -3:].sum() > 0, hits[-2:, :3].sum() > 0, hits[-2:, -3:].sum() > 0]
    return frac, all(corners)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--square-mm", type=float, required=True, help="MEASURED printed square size")
    ap.add_argument("--marker-mm", type=float, help="measured marker size (default 0.75 x square)")
    ap.add_argument("--name", required=True, help="label for this setting, e.g. wide_4k_30_rocksteady")
    ap.add_argument("--max-frames", type=int, default=80)
    ap.add_argument("--allow-no-metadata", action="store_true",
                    help="accept clips without DJI metadata (not recommended)")
    args = ap.parse_args()

    out_dir = os.path.join("results", args.name)
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    log = lambda s: (print(s), lines.append(s))

    # 1. settings must be identical across clips
    settings = [read_settings.read(p) for p in args.clips]
    if not all(s["metadata"] for s in settings) and not args.allow_no_metadata:
        sys.exit("ERROR: some clips have no DJI metadata (copied via phone app / re-encoded?). "
                 "Copy files straight off the microSD card, or pass --allow-no-metadata.")
    keyf = lambda s: (s.get("lens_mode_code"), s.get("width"), s.get("height"), s.get("fps"),
                      s.get("stabilization_code"))
    keys = {keyf(s) for s in settings}
    if len(keys) > 1:
        sys.exit(f"ERROR: clips were recorded with different settings: {keys}")
    st = settings[0]
    log(f"setting: lens mode {st.get('lens_mode_code')} ({st.get('lens_mode')}), "
        f"{st.get('width')}x{st.get('height')} @ {st.get('fps')} fps, stabilization {st.get('stabilization')}, "
        f"firmware {st.get('firmware')}")

    # 2. detect + select
    sq = args.square_mm / 1000
    mk = (args.marker_mm / 1000) if args.marker_mm else sq * make_board.BOARD["marker_ratio"]
    d = cv2.aruco.getPredefinedDictionary(make_board.BOARD["dictionary"])
    board = cv2.aruco.CharucoBoard((make_board.BOARD["squares_x"], make_board.BOARD["squares_y"]), sq, mk, d)
    frames, size = detect(args.clips, board)
    log(f"board found in {len(frames)} sampled frames")
    if len(frames) < 40:
        sys.exit("ERROR: too few usable frames. Check lighting/blur, board flatness, and --square-mm.")
    chosen = select(frames, size, args.max_frames + args.max_frames // 4)
    held = chosen[4::5]                       # every 5th selected frame is never used for fitting
    train = [f for k, f in enumerate(chosen) if k % 5 != 4]

    # 3. fit + evaluate
    rms, K, D, per, train = fit_robust(train, board, size, log)
    ho = holdout_rms(held, board, K, D)
    ok_corner, reach, corner = valid_to_corners(K, D, size)
    lam = lambda_equiv(K, D, size)
    cov, all_corners = coverage(train + held, size, os.path.join(out_dir, "coverage.png"))

    s = size[0] / 1920
    checks = {
        f"held-out RMS {ho:.3f} px <= {0.5 * s:.2f}": ho <= 0.5 * s,
        f"coverage {cov:.0%} of grid >= 80%": cov >= 0.8,
        "board reached all four corner regions": all_corners,
        f"model valid to corners (reach {reach:.0f} px vs corner {corner:.0f} px)": ok_corner,
        f"frames used {len(train)} >= 30": len(train) >= 30,
    }
    log(f"fit RMS {rms:.3f} px on {len(train)} frames; held-out RMS {ho:.3f} px on {len(held)} frames")
    log(f"fx {K[0, 0]:.2f}  fy {K[1, 1]:.2f}  cx {K[0, 2]:.2f}  cy {K[1, 2]:.2f}  "
        f"k1..k4 {np.round(D.ravel(), 5).tolist()}  lambda-equivalent {lam:.3f}")
    for k, v in checks.items():
        log(f"  [{'PASS' if v else 'FAIL'}] {k}")
    verdict = all(checks.values())
    log("RESULT: " + ("PASS" if verdict else "FAIL: see the failed checks; usually more board views "
                      "near the frame corners or sharper frames fix it"))

    entry = {
        "name": args.name,
        "lens_mode_code": st.get("lens_mode_code"), "lens_mode": st.get("lens_mode"),
        "width": size[0], "height": size[1], "fps": st.get("fps"),
        "stabilization": st.get("stabilization"), "firmware": st.get("firmware"),
        "model": "OPENCV_FISHEYE", "distortion_model": "opencv_fisheye_4",
        "K": K.tolist(), "fx": K[0, 0], "fy": K[1, 1], "cx": K[0, 2], "cy": K[1, 2],
        "distortion_coeffs": D.ravel().tolist(),
        "reprojection_error_px": rms, "holdout_reprojection_error_px": ho,
        "frames_used": len(train), "frames_held_out": len(held), "coverage": cov,
        "valid_to_corners": ok_corner, "lambda_equivalent": lam,
        "square_mm": args.square_mm, "clips": [os.path.basename(p) for p in args.clips],
        "checks_passed": verdict,
    }
    with open(os.path.join(out_dir, "intrinsics_entry.json"), "w") as f:
        json.dump(entry, f, indent=1)
    with open(os.path.join(out_dir, "report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out_dir}/intrinsics_entry.json, coverage.png, report.txt")
    return 0 if verdict else 2


if __name__ == "__main__":
    sys.exit(main())
