# Step 1: settings mapping

Camera: DJI Osmo Action 5 Pro
Firmware: **10.00.16.13** (within the dataset range 10.00.14.45 to 10.00.16.x)
Clips: `DCIM/DJI_001/DJI_20261002211830_0002_D.MP4` … `_0008_D.MP4`, recorded 2026-10-02, read with `tools/read_settings.py` straight off the microSD card. All 1920x1080 @ 29.97.

| Clip | Menu: FOV | Menu: stabilization | lens mode code | stabilization reported |
|---|---|---|---|---|
| 0002 | Standard | Off | 2 (standard) | off (code 0) |
| 0003 | Wide | Off | 1 (wide) | off (code 0) |
| 0004 | Ultra Wide | Off | **3** | off (code 0) |
| 0005 | Standard | RockSteady | 2 | RockSteady (code 1) |
| 0006 | Standard | RockSteady+ | 2 | **RockSteady+ (code 4)** |
| 0007 | Standard | HorizonBalancing | 2 | HorizonBalancing (code 5) |
| 0008 | Standard | HorizonSteady | 2 | HorizonSteady (code 2) |

Findings:

- **Lens mode code 3 = Ultra Wide.**
- **Stabilization code 4 = RockSteady+.** Older `read_settings.py` labelled it "Tradeoff"; the tool and the session list now use the menu name (settings `ultrawide_*_rocksteadyplus`, formerly `m3_*_tradeoff`).
- Wide + stabilization off writes DJI's lens profile (clip 0003): `f=728.54 px`, `k=[0.15513, 0.13714, -0.09386, 0.00417]` at 1920x1080. Standard and Ultra Wide with stabilization off write none.
- The same mapping and the same DJI lens profile were first seen on firmware 10.00.00.24, before updating to 10.00.16.13. The firmware update did not change them.
