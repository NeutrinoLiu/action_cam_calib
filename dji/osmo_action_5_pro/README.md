# DJI Osmo Action 5 Pro

Camera: DJI Osmo Action 5 Pro, firmware **10.00.16.13** (inside the dataset range 10.00.14.45 to 10.00.16.x).
Recorded 2026-10-03, calibrated 2026-10-04. Model: OpenCV fisheye (`OPENCV_FISHEYE`, k1..k4), as requested.

## 1. Summary

- **7 of the 9 recorded settings are calibrated and pass every `calibrate.py` check.** All 4 priority-1 settings are among them; together the 7 cover about 88 % of the dataset by the handover's shares.
- **Lens mode code 3 is Ultra Wide, and stabilization code 4 ("Tradeoff") is RockSteady+.**
- **Ultra Wide + RockSteady+ cannot be calibrated with fixed intrinsics.** With the camera on a tripod, its principal point drifts by 100–200 px within a single clip. This affects the ~5 % of the dataset with lens mode code 3 (finding 2).
- **Frame rate does not change the intrinsics** (25 vs 29.97 fps), and **4K and 1080p Wide have the same field of view**.
- **RockSteady moves the principal point by a few pixels between recordings** (finding 5).
- **Our focal length is 2.6 % below DJI's own lens profile** for Wide with stabilization off, with an identical distortion shape. The cause is unresolved (finding 6).
- **`calibrate.py` needed two fixes** to run on this footage (section 5). Both are included and the self-test passes.

## 2. Results

A+B calibrations, 200 frames each, `--square-mm 20`. Each `intrinsics_entry.json` is in `results/<setting>/<setting>/`; `intrinsics.json` collects the passing ones.

| Setting | Lens code | Stab. | fx | fy | cx | cy | Held-out RMS | λ-equiv. | Checks |
|---|---|---|---|---|---|---|---|---|---|
| `wide_3840x2160_30_rocksteady` | 1 | RockSteady | 1557.16 | 1564.14 | 1921.38 | 1072.11 | 0.36 px | 0.276 | PASS |
| `std_1920x1080_30_rocksteady` | 2 | RockSteady | 775.01 | 778.48 | 958.33 | 537.60 | 0.27 px | 0.008 | PASS |
| `std_1920x1080_25_rocksteady` | 2 | RockSteady | 773.33 | 776.73 | 957.60 | 536.08 | 0.25 px | 0.008 | PASS |
| `wide_3840x2160_30_off` (reference) | 1 | off | 1416.12 | 1422.20 | 1919.90 | 1070.23 | 0.48 px | 0.351 | PASS |
| `wide_1920x1080_30_rocksteady` | 1 | RockSteady | 781.68 | 785.58 | 958.58 | 533.38 | 0.28 px | 0.270 | PASS |
| `std_1920x1080_30_horizonsteady` | 2 | HorizonSteady | 993.07 | 998.06 | 958.21 | 535.11 | 0.27 px | 0.002 | PASS |
| `wide_3840x2880_25_rocksteady` | 1 | RockSteady | 1565.82 | 1573.09 | 1918.01 | 1433.12 | 0.64 px | 0.272 | PASS |
| `ultrawide_1920x1080_30_rocksteadyplus` | 3 | RockSteady+ | — | — | — | — | 2.93 px | — | **FAIL** |
| `ultrawide_3840x2160_30_rocksteadyplus` | 3 | RockSteady+ | — | — | — | — | 6.29 px | — | **FAIL** |

For all 7 calibrated settings, coverage is 100 % with all four corners reached, and the model is valid to the corners.

Distortion coefficients (OpenCV fisheye, θ_d = θ (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸)), same A+B calibrations:

| Setting | k1 | k2 | k3 | k4 |
|---|---|---|---|---|
| `wide_3840x2160_30_rocksteady` | 0.17121 | 0.08378 | −0.02746 | −0.02481 |
| `std_1920x1080_30_rocksteady` | 0.35784 | −0.01167 | 0.28417 | −0.11622 |
| `std_1920x1080_25_rocksteady` | 0.35531 | 0.00412 | 0.25643 | −0.10112 |
| `wide_3840x2160_30_off` (reference) | 0.15889 | 0.12392 | −0.07439 | −0.00495 |
| `wide_1920x1080_30_rocksteady` | 0.18658 | 0.03144 | 0.04034 | −0.05392 |
| `std_1920x1080_30_horizonsteady` | 0.37957 | −0.15401 | 0.62443 | −0.38456 |
| `wide_3840x2880_25_rocksteady` | 0.17740 | 0.06228 | 0.00051 | −0.03608 |

The four coefficients are strongly correlated: two fits can differ coefficient by coefficient yet trace the same curve. Compare settings by the resulting distortion curve (or λ-equivalent), not by individual k values.

**A vs B repeatability** (A-only and B-only calibrations, compared to the handover's limits):

| Setting | A-only / B-only checks | fx difference (limit 0.3 %) | cx/cy max difference (limit 2 px at 1080p, 4 px at 4K) |
|---|---|---|---|
| `wide_3840x2160_30_rocksteady` | PASS / PASS | 0.17 % | **8.2 px** |
| `std_1920x1080_30_rocksteady` | PASS / PASS | 0.11 % | 1.2 px |
| `std_1920x1080_25_rocksteady` | PASS / PASS | 0.27 % | 2.0 px |
| `wide_3840x2160_30_off` | PASS / PASS | 0.29 % | 1.4 px |
| `wide_1920x1080_30_rocksteady` | PASS / PASS | 0.15 % | **2.9 px** |
| `std_1920x1080_30_horizonsteady` | PASS / PASS | **0.37 %** | 1.8 px |
| `wide_3840x2880_25_rocksteady` | PASS / **FAIL**¹ | 0.03 % | 1.4 px |

¹ The B-only model is valid to 2405 px; the farthest corner is 2407 px. This is a 2 px miss, and the A+B calibration passes.

The two cx/cy misses are both Wide with RockSteady; finding 5 explains them.

## 3. Step 1: settings mapping

Full table in `settings_mapping.md`. The mapping is the same on firmware 10.00.00.24 and 10.00.16.13.

| Menu FOV | Lens mode code | | Menu stabilization | Stabilization code |
|---|---|---|---|---|
| Wide | 1 | | Off | 0 |
| Standard | 2 | | RockSteady | 1 |
| **Ultra Wide** | **3** | | HorizonSteady | 2 |
| | | | **RockSteady+** (was "Tradeoff") | **4** |
| | | | HorizonBalancing | 5 |

`read_settings.py` now prints "ultra wide" and "RockSteady+". In the session list, `m3_*_tradeoff` was renamed `ultrawide_*_rocksteadyplus`.

## 4. Findings

**1. Wide and Standard are well described by the fisheye model.** Residuals are about 0.2 px uniformly from the centre to the frame edges. Fits on separate quarters of a clip agree on cx/cy within a few pixels.

**2. Ultra Wide + RockSteady+ has no fixed intrinsics.** Even a fit on a quarter of one clip (about 20 s, camera on a tripod) leaves 2–3 px RMS. Across the quarters of the 1080p clips, the principal point moves from cx 845 to 987 and from cy 457 to 672. For comparison, Standard quarters fit at 0.24–0.30 px, with cx 958–967 and cy 535–542. RockSteady+ evidently keeps moving and warping its crop window. A single `intrinsics.json` entry can't represent code-3 clips. Options: estimate intrinsics per clip during SLAM, or exclude those clips. The failed results are still included, as evidence.

**3. Frame rate does not matter.** Standard at 25 vs 29.97 fps: fx differs by −0.22 % and the principal point by under 1.5 px, both within the A-vs-B spread. Based on this, `wide_1920x1080_60_rocksteady` was **not recorded**; use the 29.97 fps Wide entry. 59.94 fps itself was not tested, and a higher frame rate could use a different sensor readout.

**4. 4K and 1080p Wide have the same field of view.** For Wide + RockSteady, 4K fx/2 = 778.6 vs 1080p fx = 781.7 (−0.4 %).

**5. RockSteady shifts the principal point between recordings.** For Wide + RockSteady, cx/cy differ between A and B by 2.9 px at 1080p and 8.2 px at 4K. With stabilization off the difference is 1.4 px at 4K. Recording more carefully would not change this: the stabilizer places its crop slightly differently each time. The MOTION clips are there to quantify how much it moves during handheld use.

**6. Focal length is 2.6 % below DJI's lens profile.** With Wide and stabilization off, the camera writes its own profile into the file: f = 1457.07 px at 4K, k = [0.15513, 0.13714, −0.09386, 0.00417]. Our image radius is a uniform 2.5–2.6 % smaller than DJI's from 10° to 60° off axis (−2.9 % at 70°). So the distortion shape agrees and only the scale differs. This is far bigger than our A/B spread, so it's systematic rather than noise. The old calibration's fx at 1920 wide (~804 for Wide, ~802 for Standard) is also about 3 % above our 781.7 and 775.0, but its settings are unknown. Possible explanations:
- DJI's profile is generic rather than measured per unit.
- A systematic bias in our setup. The board was a scaled A4 print, and its flatness and backing were not recorded.

We recommend checking against the dataset footage before using these entries for SLAM.

**7. fx/fy = 0.995 in every setting, including stabilization off.** Square pixels would give 1.000. The most likely cause is a print scaled ~0.45 % differently horizontally and vertically (see `board.txt`); the second direction was not measured. If you treat the pixels as square, set fx = fy = (fx + fy)/2. The effect is about ±0.2 % per axis, which is about 2 px at the edge of a 1080p frame.

**8. λ-equivalent vs the dataset ranges.** Wide + RockSteady: 0.270–0.276, inside 0.19–0.29. Standard: 0.002–0.008, just above the measured −0.03–0.0. Wide with stabilization off: 0.351, higher than 0.29, as expected for the uncropped image; there is no dataset counterpart.

## 5. Changes to the kit tools

The modified files are in [`pipeline/`](../../pipeline/). With these changes the self-test passes (`SELFTEST: PASS`; held-out 0.266 px, 99th-percentile image error 0.91 px).

1. **`calibrate.py`: fallback fit.** `cv2.fisheye.calibrate` crashed (`InitExtrinsics: fabs(norm_u1) > 0`) on 7 of the 27 runs and needed the existing drop-a-frame retries on 6 more. Each iteration it recomputes every frame's pose from undistorted points. With wide frames, some intermediate distortion estimate stops being invertible at the frame edge, and the call aborts. Dropping frames did not help. When the call fails, `fit_lm()` now minimises the same reprojection error with Levenberg–Marquardt, using only the forward projection. Where OpenCV succeeds, both give identical fx, fy, cx, cy and k1..k4 to every digit compared. Settings that already worked are unchanged.
2. **`calibrate.py`: held-out check.** The held-out pose came from PnP on undistorted points. A single point that OpenCV could not undistort (it returns −1e6), or a few points near 90° off axis, would ruin the pose and give held-out RMS values of 150–15 000 px for good fits. The pose is now initialised from points within 60° of the axis, then refined in pixel space using all points.
3. **`--max-frames 200` instead of the default 80.** With 80 frames, A and B disagreed on fx by up to 0.78 %; with 200 they agree within 0.37 %. Each run detects the board in about 900 sampled frames.
4. **OpenCV 4.14.0** (`opencv-contrib-python<5`). OpenCV 5.0.0 narrowly fails the self-test (99th-percentile image error 1.09 px, limit 1.0) and was not used.
5. **`read_settings.py`:** labels only. Code 3 → "ultra wide"; code 4 → "RockSteady+".

## 6. Deviations from the handover

- **Board:** printed at ~71 % (20 mm squares instead of 28 mm), with the 100 mm bar and the second direction not measured. See `board.txt`.
- **Firmware** was updated from 10.00.00.24 to 10.00.16.13 before any calibration footage was recorded.
- **No check clips** were recorded before each setting. Every calibration clip's metadata was verified afterwards with `read_settings.py`, and all of them match their settings (`calibrate.py` also enforces this).
- **Not recorded:**
  - `wide_1920x1080_60_rocksteady` (see finding 3)
  - the rare combinations under 1 % that the handover didn't list
- **Three B clips are shorter than 60 s:** horizonsteady B 50 s, 4:3 B 57 s, Ultra Wide 4K B 44 s. Their calibrations still pass, apart from Ultra Wide.
- **MOTION clips** were recorded for every setting, not just priority 1. In each, the board stays fixed and the camera is moved naturally, with a few seconds held still at the start and end.

## 7. Files in this folder

```
README.md                 this report
intrinsics.json           the 7 passing A+B entries, one list (calibrate.py's entry format)
settings_mapping.md       Step 1 table, firmware
board.txt                 board print and measurements
capture_log.json          recording log: every take, file number, result
results/<setting>/        one folder per recorded setting (9)
    <setting>/            A+B: intrinsics_entry.json, coverage.png, report.txt
    <setting>_A_only/
    <setting>_B_only/
```

The videos (about 10 GB) are not in the repository. All were copied straight from the microSD card, MD5-verified against it, and keep their DJI metadata. With the clips laid out as `<root>/<setting>/CAL_<setting>_{A,B}.MP4`, everything here is reproduced by:

```bash
pip install -r pipeline/requirements.txt
python pipeline/run_batch.py <root> --square-mm 20 --max-frames 200
```
