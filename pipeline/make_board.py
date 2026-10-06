#!/usr/bin/env python3
"""Render the ChArUco calibration board as a print-ready PNG (default: A3 landscape, 300 dpi).

The board definition (square count, dictionary, marker/square ratio) must match what
calibrate.py expects, so both read BOARD below. Print at 100% scale ("actual size",
never "fit to page"), then MEASURE the printed square size and pass it to calibrate.py.

Usage:
    python make_board.py                     # -> charuco_A3_12x9.png
    python make_board.py --paper A2          # larger board for >1.5 m distances
"""
import argparse
import cv2
import numpy as np

# Shared board definition (calibrate.py imports this).
BOARD = dict(squares_x=12, squares_y=9, dictionary=cv2.aruco.DICT_6X6_250, marker_ratio=0.75)
PAPER_MM = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420)}


def board(square_m=0.03):
    d = cv2.aruco.getPredefinedDictionary(BOARD["dictionary"])
    return cv2.aruco.CharucoBoard((BOARD["squares_x"], BOARD["squares_y"]), square_m,
                                  square_m * BOARD["marker_ratio"], d)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--paper", default="A3", choices=PAPER_MM)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    pw, ph = PAPER_MM[args.paper]
    margin = 15                                            # mm of white border on each side
    sq = min((pw - 2 * margin) / BOARD["squares_x"], (ph - 2 * margin - 10) / BOARD["squares_y"])
    sq = np.floor(sq)                                      # whole mm squares are easier to verify
    px = lambda mm: int(round(mm / 25.4 * args.dpi))
    W, H = px(pw), px(ph)
    img = np.full((H, W), 255, np.uint8)
    bw, bh = px(sq * BOARD["squares_x"]), px(sq * BOARD["squares_y"])
    art = board(sq / 1000).generateImage((bw, bh), marginSize=0, borderBits=1)
    x0, y0 = (W - bw) // 2, px(margin)
    img[y0:y0 + bh, x0:x0 + bw] = art
    # 100 mm scale bar + note, so a wrong print scale is caught before recording
    yb = y0 + bh + px(4)
    cv2.rectangle(img, (x0, yb), (x0 + px(100), yb + px(2)), 0, -1)
    txt = (f"ChArUco {BOARD['squares_x']}x{BOARD['squares_y']}  DICT_6X6_250  square {sq:.0f} mm  "
           f"marker {sq * BOARD['marker_ratio']:.1f} mm  |  bar = 100 mm: measure it. Print at 100% scale.")
    cv2.putText(img, txt, (x0 + px(105), yb + px(2)), cv2.FONT_HERSHEY_SIMPLEX, args.dpi / 300 * 1.0, 0, 2,
                cv2.LINE_AA)
    out = f"charuco_{args.paper}_{BOARD['squares_x']}x{BOARD['squares_y']}.png"
    cv2.imwrite(out, img)
    print(f"wrote {out}: {args.paper} at {args.dpi} dpi, nominal square {sq:.0f} mm "
          f"(measure the print; pass the measured value to calibrate.py --square-mm)")


if __name__ == "__main__":
    main()
