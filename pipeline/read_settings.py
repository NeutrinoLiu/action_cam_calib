#!/usr/bin/env python3
"""Print the recording settings a DJI Osmo Action 5 Pro wrote into an MP4.

Reads the first packet of the camera's "djmd" metadata track (protobuf) and prints
the fields that decide which intrinsics a clip needs:

    lens mode code   field 2.5.1  (1 = wide, 2 = standard, 3 = ultra wide)
    resolution, fps  fields 2.3.1 / 2.3.2 / 2.3.3
    stabilization    field 1.9.1  (0 off, 1 RockSteady, 2 HorizonSteady, 4 RockSteady+, ...)
    firmware         field 1.1.6
    DJI lens profile fields 1.3 (fisheye k1..k4) and 1.8 (focal length, px), written
                     only when FOV = Wide and stabilization is off

Usage:
    python read_settings.py clip1.MP4 [clip2.MP4 ...]
    python read_settings.py --json clip.MP4          # machine-readable

Requires: Python 3.8+ and ffmpeg/ffprobe on PATH. No other packages.
"""
import argparse
import json
import struct
import subprocess
import sys

EIS = {0: "off", 1: "RockSteady", 2: "HorizonSteady", 3: "Hyper", 4: "RockSteady+",
       5: "HorizonBalancing", 6: "DeepSpace", 7: "off (with crop)", 8: "HorizonCorrection",
       9: "RockSteady auto"}
LENS = {1: "wide", 2: "standard", 3: "ultra wide"}


def first_djmd_packet(path):
    """Raw bytes of the first packet of the 'djmd' data stream, or None."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=index,codec_tag_string", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    idx = [ln.split(",")[0] for ln in out.split() if ln.endswith("djmd")]
    if not idx:
        return None
    pkt = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", f"0:{idx[0]}",
                          "-c", "copy", "-frames:d", "1", "-f", "data", "-"],
                         capture_output=True).stdout
    return pkt or None


def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return r, i


def fields(b):
    """One protobuf message level -> {field_number: [(wire_type, value), ...]}."""
    out, i = {}, 0
    while i < len(b):
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        elif wt == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        else:
            raise ValueError("unsupported wire type")
        out.setdefault(f, []).append((wt, v))
    return out


def get(msg, *path):
    """Follow a field path through nested messages; returns the last (wt, value) or None."""
    cur = msg
    for k, f in enumerate(path):
        if f not in cur:
            return None
        wt, v = cur[f][0]
        if k == len(path) - 1:
            return wt, v
        cur = fields(v)
    return None


def floats(raw):
    """Repeated float: packed bytes or a single fixed32."""
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def read(path):
    pkt = first_djmd_packet(path)
    if pkt is None:
        return {"file": path, "metadata": False,
                "note": "no DJI metadata track: file was re-encoded or not straight off the camera"}
    top = fields(pkt)
    res = {"file": path, "metadata": True}
    v = get(top, 1, 1, 6)
    res["firmware"] = v[1].decode(errors="replace") if v else None
    v = get(top, 2, 3, 1); res["width"] = v[1] if v else None
    v = get(top, 2, 3, 2); res["height"] = v[1] if v else None
    v = get(top, 2, 3, 3); res["fps"] = round(struct.unpack("<f", v[1])[0], 3) if v else None
    v = get(top, 2, 5, 1); res["lens_mode_code"] = v[1] if v else None
    res["lens_mode"] = LENS.get(res["lens_mode_code"], "unknown")
    v = get(top, 1, 9, 1)
    eis = v[1] if v else 0          # proto3 omits a zero enum, so "absent" means off
    res["stabilization_code"] = eis
    res["stabilization"] = EIS.get(eis, f"code {eis}")
    k = get(top, 1, 3, 1)
    f = get(top, 1, 8, 1)
    if k and f:
        res["dji_lens_profile"] = {"model": "OpenCV fisheye", "focal_px": floats(f[1])[0],
                                   "k1_k4": floats(k[1]), "principal_point": "image centre"}
    else:
        res["dji_lens_profile"] = None
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()
    rows = [read(p) for p in args.files]
    if args.json:
        print(json.dumps(rows, indent=1))
        return
    for r in rows:
        print(r["file"])
        if not r["metadata"]:
            print("  !!", r["note"])
            continue
        print(f"  lens mode      : {r['lens_mode']} (code {r['lens_mode_code']})")
        print(f"  resolution/fps : {r['width']}x{r['height']} @ {r['fps']}")
        print(f"  stabilization  : {r['stabilization']} (code {r['stabilization_code']})")
        print(f"  firmware       : {r['firmware']}")
        p = r["dji_lens_profile"]
        print("  DJI lens prof. : " + (f"f={p['focal_px']:.2f}px k={['%.5f' % x for x in p['k1_k4']]}"
                                       if p else "not present"))


if __name__ == "__main__":
    sys.exit(main())
