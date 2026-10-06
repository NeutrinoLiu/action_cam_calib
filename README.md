# action_cam_calib

Intrinsic calibration of action cameras for egocentric SLAM (EgoVerse), one calibration per recording setting. Each camera has its own folder of results and findings; the pipeline is shared.

> [!TIP]
> If this repo saves you time, please give it a ⭐ — it helps others find it.

| Camera | Folder | Status |
|---|---|---|
| DJI Osmo Action 5 Pro (firmware 10.00.16.13) | [`dji/osmo_action_5_pro/`](dji/osmo_action_5_pro/) | 7 settings calibrated (~88 % of the dataset). Ultra Wide + RockSteady+ cannot be calibrated with fixed intrinsics. |

## Layout

```
README.md                     this file: layout, quick start, methodology
pipeline/
    calibrate.py              calibrate one setting from ChArUco clips (OpenCV fisheye)
    run_batch.py              A+B, A-only and B-only calibrations for every setting folder
    read_settings.py          print the settings a DJI camera wrote into an MP4
    make_board.py             generate the ChArUco board
    charuco_A3_12x9.png       the board, for A3 at 100 %
    selftest.py               install check on synthetic footage of a known camera
    capture_log.py/.html      local page that guides and logs a recording session
    requirements.txt
dji/osmo_action_5_pro/
    README.md                 findings and results
    intrinsics.json           the calibrated entries
    results/                  every calibration: intrinsics_entry.json, coverage.png, report.txt
    settings_mapping.md, board.txt, capture_log.json
```

`calibrate.py`, `read_settings.py`, `make_board.py`, `selftest.py` and the board come from the EgoVerse calibration kit. `calibrate.py` has two fixes made here (see [Fitting](#fitting) and [Evaluation](#evaluation)). `run_batch.py` and `capture_log` are new.

## Quick start

```bash
pip install -r pipeline/requirements.txt     # OpenCV 4.x: 5.0 narrowly fails the self-test
python pipeline/selftest.py                  # ends with SELFTEST: PASS
```

1. **Board.** Print `pipeline/charuco_A3_12x9.png` at 100 % on matte paper and mount it on something rigid and flat. Measure the square size in **both** directions.
2. **Find the settings.** Record 5 s per FOV option and per stabilization option. Map menu names to metadata codes with `python pipeline/read_settings.py *.MP4`.
3. **Record.** `python pipeline/capture_log.py` opens a page with each setting's menu values, the shooting hints and a log of every take. Record A, B and MOTION per setting (see the [protocol](#recording-protocol)).
4. **Copy.** Copy the MP4s straight off the card, never through a phone app (that strips the metadata). Lay them out as `<root>/<setting>/CAL_<setting>_A.MP4`, `CAL_<setting>_B.MP4` and `MOTION_<setting>.MP4`.
5. **Calibrate.** `python pipeline/run_batch.py <root> --square-mm <measured> --max-frames 200`
6. **Check.** Look at each `report.txt` and `coverage.png`, and at the A-vs-B agreement (see [Evaluation](#evaluation)).

## Methodology

### Why per setting

Every clip in the dataset was recorded with electronic stabilization, which crops and warps the image. Intrinsics are therefore valid only for the exact combination of FOV (lens mode), resolution, frame rate and stabilization a clip was recorded in. The setting is always read from the file's metadata, never from memory. `calibrate.py` refuses to combine clips whose metadata differ.

`read_settings.py` decodes the first packet of the camera's `djmd` protobuf track:

| Field | Meaning |
|---|---|
| 2.5.1 | lens mode code |
| 2.3.1 / 2.3.2 / 2.3.3 | width / height / fps |
| 1.9.1 | stabilization code (an absent field means off) |
| 1.1.6 | firmware |
| 1.3 / 1.8 | DJI's own fisheye profile (written only for Wide with stabilization off) |

### Board

- ChArUco, 12 × 9 squares, `DICT_6X6_250`, marker = 0.75 × square. Partly visible boards still yield corners; a frame counts with ≥ 12 corners.
- **Scale does not matter, anisotropy does.** A uniformly scaled print gives the same K and distortion; only board-to-camera distances scale. We checked this: the same frames calibrated with 20 mm and 28 mm give identical fx, fy, cx, cy and k1..k4. A print stretched differently in x and y shows up as fx/fy ≠ 1. Measure both directions.
- Flatness and rigidity matter more than size accuracy.

### Recording protocol

- **Camera on a tripod, completely still; move the board.** Moving the camera makes the stabilizer warp the image.
- **A and B, 60–90 s each, recorded independently.** Each covers the whole frame. Two clips give a repeatability check, and their union gives the final fit.
- **Board positions.** Corners first, then edges, then the centre, at 20–60 % of the frame width (0.4–1.2 m). Every position gets two holds of about 1 s each:
  - **centre:** board parallel to the sensor, then tilted 30–45°;
  - **edges and corners:** board facing the lens, then turned about 20°, **never away from the lens**.

  At Wide's corners the line of sight is about 70° off axis, so a board held parallel to the sensor there is seen at about 70° and its markers are not detected. Rotate the tilt direction between positions. Frames taken while the board is moving are mostly discarded as blurry.
- **MOTION, about 30 s.** The board is fixed to a wall or table and the camera is moved as in real recording (head-mounted if possible), still for a few seconds at the start and end. This quantifies how much the stabilizer moves the image. It is not used for calibration.
- **Log every take** with its file number, including failed ones with the reason (`capture_log`). DJI file numbers run sequentially, so the log maps files to slots.

### Detection and frame selection

1. **Detect.** Sample about 900 frames evenly across the clips and run the ChArUco detector. For each hit, keep the corners and a sharpness score: the variance of the Laplacian inside the board's bounding box.
2. **Select.** Drop the blurriest third. Then pick frames greedily by how many cells of a 12 × 8 image grid they cover that have been seen fewer than 3 times (plus a small bonus for corner count), up to `max_frames × 1.25`.
3. **Hold out** every 5th selected frame. Held-out frames are never fitted.

`--max-frames 200` instead of the default 80. With 80, A-only and B-only fx disagreed by up to 0.78 %; with 200 they agree within 0.37 % (usually under 0.3 %). The extra frames cut estimation noise, mostly in the focal length.

### Fitting

- **Model:** OpenCV fisheye, θ_d = θ (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸). Parameters fx, fy, cx, cy, k1..k4, skew fixed at 0. Start: f = 0.42 W, principal point at the image centre, k = 0.
- **Solver:** `cv2.fisheye.calibrate` with `CALIB_RECOMPUTE_EXTRINSIC`. If it aborts, a Levenberg–Marquardt fallback (`fit_lm`) is used.
  - Why it aborts: `cv2.fisheye.calibrate` recomputes every frame's pose from undistorted points on each iteration. On wide footage an intermediate distortion estimate stops being invertible near the frame edge, and the call fails with `InitExtrinsics: fabs(norm_u1) > 0`. Dropping frames, a two-stage start (k1 first) and a centre-out start all failed to prevent it.
  - What the fallback does: it minimises the same pixel reprojection error over intrinsics and all frame poses jointly, eliminating the poses with a Schur complement, and uses only the forward projection, which is always defined.
  - Where OpenCV converges, the two agree to every digit compared.
- **Outlier frames:** refit and drop the worst frame while its RMS exceeds max(3 × median, 1 px × W/1920), for up to 15 % of frames.

### Evaluation

| Check (from `calibrate.py`, scaled by W/1920) | Pass |
|---|---|
| held-out reprojection RMS | ≤ 0.5 px |
| grid coverage | ≥ 80 %, all four corner regions |
| model valid to the corners | f · θ_d(θ) still increasing at the farthest corner |
| frames used | ≥ 30 |

- **Held-out pose.** Each held-out frame's pose comes from PnP on undistorted points within 60° of the axis, then is refined in pixel space using all points, and the error is scored on all points. Previously the pose came from PnP on all points. One point OpenCV could not undistort (it returns −1e6), or a few points near 90° off axis, then wrecked it and reported 150–15 000 px for good fits.
- **Repeatability (A-only vs B-only).** fx within 0.3 %; cx/cy within 2 px at 1080p and 4 px at 4K.
- **Plausibility.**
  - `lambda_equivalent` is compared with the ranges measured on dataset footage.
  - For Wide with stabilization off, the result is compared with DJI's own profile from the file. Compare the image-radius curve r(θ) = f · θ_d(θ), not f or individual k values: the k coefficients are strongly correlated, and fits with different k can trace the same curve.

### Diagnostics

These are useful when a setting misbehaves:

- **Stationarity.** Fit each quarter of a clip separately. Stable intrinsics give matching cx/cy and similar RMS. This is how Ultra Wide + RockSteady+ was found to drift (cx 845 → 987 and cy 457 → 672 within one clip, 2–3 px RMS even per quarter).
- **Residuals by image region.** Uniform residuals of about 0.2 px mean the model fits. Large residuals everywhere mean the image is not described by one static radial model.
- **Square size swap.** Identical intrinsics confirm the fit is not sensitive to board scale.

## Known limitations

- **Stabilized modes are not static cameras.** RockSteady shifts the principal point by a few pixels between recordings: 2.9 px at 1080p and 8.2 px at 4K for Wide, against 1.4 px with stabilization off. RockSteady+ with Ultra Wide drifts by 100–200 px.
- **Focal length vs DJI.** For the Osmo Action 5 Pro, our focal length is 2.6 % below DJI's embedded profile, with the same curve shape. The cause is unresolved; see the camera's README, finding 6.
