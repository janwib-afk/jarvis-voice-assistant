"""Pixel-Diff zweier Screenshot-Ordner (Phase-1-Regressionspruefung).

Vergleicht gleichnamige PNGs aus <dir_a> und <dir_b> pixelweise (Pillow).
Gedacht fuer --freeze-Laeufe von capture_baseline.py (fixe Uhr, Animationen aus),
bei denen jede Abweichung eine echte visuelle Regression ist.

Nutzung:  python docs/design-system/tools/diff_screens.py <dir_a> <dir_b> [--report out.md]
Exit 0 = alle Bilder identisch; Exit 1 = Abweichungen oder fehlende Bilder.
"""

import os
import sys

from PIL import Image, ImageChops


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dir_a, dir_b = sys.argv[1], sys.argv[2]
    report_path = None
    if "--report" in sys.argv:
        report_path = sys.argv[sys.argv.index("--report") + 1]

    names_a = {n for n in os.listdir(dir_a) if n.lower().endswith(".png")}
    names_b = {n for n in os.listdir(dir_b) if n.lower().endswith(".png")}

    rows = []
    failed = False

    for name in sorted(names_a | names_b):
        if name not in names_a or name not in names_b:
            rows.append((name, "FEHLT in " + ("B" if name in names_a else "A"), ""))
            failed = True
            continue
        a = Image.open(os.path.join(dir_a, name)).convert("RGB")
        b = Image.open(os.path.join(dir_b, name)).convert("RGB")
        if a.size != b.size:
            rows.append((name, f"GROESSE {a.size} vs {b.size}", ""))
            failed = True
            continue
        diff = ImageChops.difference(a, b)
        bbox = diff.getbbox()
        if bbox is None:
            rows.append((name, "identisch", ""))
        else:
            npix = sum(1 for p in diff.getdata() if p != (0, 0, 0))
            rows.append((name, f"{npix} Diff-Pixel", f"bbox={bbox}"))
            failed = True

    width = max(len(n) for n, _, _ in rows)
    for name, verdict, extra in rows:
        print(f"  {name:<{width}}  {verdict}  {extra}")
    total = len(rows)
    same = sum(1 for _, v, _ in rows if v == "identisch")
    print(f"\n[diff] {same}/{total} identisch — {'OK' if not failed else 'ABWEICHUNGEN'}")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Pixel-Diff-Report\n\n")
            f.write(f"- A: `{os.path.abspath(dir_a)}`\n- B: `{os.path.abspath(dir_b)}`\n")
            f.write(f"- Ergebnis: **{same}/{total} identisch**\n\n")
            f.write("| Screenshot | Ergebnis | Details |\n|---|---|---|\n")
            for name, verdict, extra in rows:
                f.write(f"| {name} | {verdict} | {extra} |\n")
        print(f"[diff] Report: {report_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
