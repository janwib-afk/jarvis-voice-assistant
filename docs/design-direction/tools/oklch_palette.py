# -*- coding: utf-8 -*-
"""Kanonische 'Warm Analog Intelligence'-Palette: OKLCH -> Hex + WCAG-Kontraste.

Pure Python (keine Abhaengigkeiten). Erzeugt deterministisch:
  - palette_table.md   (Markdown-Tabelle fuer DESIGN.md)
  - palette_root.css   (:root-Block fuer den Prototyp)

OKLCH ist die Definitionsquelle; Hex ist der Fallback. Liegt ein Zielwert
ausserhalb des sRGB-Gamuts, wird das Chroma bis zur Gamutgrenze reduziert
(vermerkt in der Tabelle).
"""

import math
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def oklch_to_srgb(L, C, H):
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return r, g, bb


def in_gamut(rgb):
    return all(-1e-6 <= c <= 1 + 1e-6 for c in rgb)


def fit_chroma(L, C, H):
    """Reduziert C bis sRGB-Gamut erreicht ist. Liefert (C_fit, geclippt?)."""
    if in_gamut(oklch_to_srgb(L, C, H)):
        return C, False
    lo, hi = 0.0, C
    for _ in range(48):
        mid = (lo + hi) / 2
        if in_gamut(oklch_to_srgb(L, mid, H)):
            lo = mid
        else:
            hi = mid
    return lo, True


def gamma(c):
    c = min(1.0, max(0.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def to_hex(L, C, H):
    C2, clipped = fit_chroma(L, C, H)
    r, g, b = (gamma(c) for c in oklch_to_srgb(L, C2, H))
    rgb = tuple(round(c * 255) for c in (r, g, b))
    return "#{:02x}{:02x}{:02x}".format(*rgb), C2, clipped


def rel_lum(hexs):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexs[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# (token, L, C, H, zweck) — Reihenfolge = Doku-Reihenfolge.
PALETTE = [
    # Flaechen
    ("bg-canvas",        0.190, 0.016, 62, "Canvas — dunkles Espresso (warm, nicht schwarz)"),
    ("bg-surface",       0.225, 0.018, 64, "primaere Oberflaeche (Journal, Panels)"),
    ("bg-raised",        0.265, 0.020, 66, "erhoehte Oberflaeche (Banner, Chips, Popover)"),
    ("bg-inset",         0.155, 0.014, 60, "eingelassene Instrumentenflaeche (Map-Bucht, Eingabe, Orb-Bett)"),
    # Text
    ("text-primary",     0.900, 0.030, 84, "Haupttext — Pergament"),
    ("text-secondary",   0.730, 0.035, 78, "Sekundaertext, Labels"),
    ("text-muted",       0.565, 0.030, 72, "gedaempfter Text (Zeitstempel, Nebeninfo)"),
    # Akzente
    ("accent-amber",     0.775, 0.125, 72, "Bernstein — Stimme/Leben: Orb, Aktivitaet, Primaeraktion"),
    ("accent-amber-deep",0.640, 0.125, 62, "Bernstein tief — pressed/aktive Kante"),
    ("brass",            0.630, 0.065, 82, "gealtertes Messing — Struktur, Fassung, ruhige Metallkanten"),
    ("brass-bright",     0.740, 0.085, 84, "helles Messing — Fokusring, Auswahlkante"),
    ("copper",           0.630, 0.105, 45, "gedaempftes Kupfer — Sekundaer-Interaktion, Links"),
    # Status
    ("success-moss",     0.630, 0.075, 128, "Erfolg — entsaettigtes Moosgruen"),
    ("warning-ember",    0.700, 0.130, 55, "Warnung — gebrannte Glut (zwischen Bernstein und Kupfer)"),
    ("error-brick",      0.585, 0.125, 30, "Fehler — warmes Ziegelrot"),
    ("info-copper",      0.680, 0.085, 48, "Information — helles Kupfer"),
    # Orb (Kern/Rand je Zustand)
    ("orb-idle-core",    0.360, 0.055, 58, "Orb idle — glimmende Kohle"),
    ("orb-idle-edge",    0.170, 0.020, 58, "Orb idle Rand"),
    ("orb-listening-core",0.760, 0.125, 70, "Orb hoert zu — ruhiges Bernstein"),
    ("orb-listening-edge",0.340, 0.075, 58, "Orb hoert zu Rand"),
    ("orb-thinking-core",0.830, 0.125, 86, "Orb denkt — helles Arbeitslicht"),
    ("orb-thinking-edge",0.420, 0.090, 78, "Orb denkt Rand"),
    ("orb-speaking-core",0.750, 0.140, 56, "Orb spricht — warmes Sprechlicht"),
    ("orb-speaking-edge",0.360, 0.090, 46, "Orb spricht Rand"),
    ("orb-muted-core",   0.235, 0.020, 58, "Orb stumm — fast erloschen"),
    ("orb-muted-edge",   0.140, 0.012, 58, "Orb stumm Rand"),
    ("orb-error-core",   0.460, 0.120, 32, "Orb Fehler — Ziegelglut"),
    ("orb-error-edge",   0.210, 0.050, 30, "Orb Fehler Rand"),
    # Schatten-Basis
    ("shadow-base",      0.100, 0.010, 60, "Schattenfarbe (warmes Braunschwarz, per Alpha)"),
]

# Alpha-Varianten: (name, basis-token, alpha, zweck)
ALPHA = [
    ("border-subtle",   "brass",         0.22, "subtile Rahmen/Trennkanten"),
    ("border-strong",   "brass-bright",  0.55, "starke Rahmen (aktive Kante)"),
    ("edge-light",      "text-primary",  0.07, "1px-Lichtkante oben (gerichtetes Licht)"),
    ("selection-bg",    "accent-amber",  0.14, "Auswahlflaeche (Text-Selektion, aktive Zeile)"),
    ("focus-halo",      "brass-bright",  0.30, "Fokusring-Halo (aussen, zusaetzlich zur 2px-Kante)"),
    ("glow-amber",      "accent-amber",  0.35, "Bernstein-Gluehen (Orb, aktive Dots)"),
    ("glow-error",      "error-brick",   0.35, "Fehler-Gluehen"),
    ("shadow-soft",     "shadow-base",   0.35, "weicher Wurfschatten (erhoehte Flaechen)"),
    ("shadow-inset",    "shadow-base",   0.55, "eingelassener Innenschatten"),
]

# Kontrastpruefungen: (vordergrund, hintergrund, mindestwert, kontext)
CHECKS = [
    ("text-primary",   "bg-canvas",  7.0, "Haupttext auf Canvas (Ziel AAA)"),
    ("text-primary",   "bg-surface", 7.0, "Haupttext auf Oberflaeche"),
    ("text-secondary", "bg-canvas",  4.5, "Sekundaertext (AA)"),
    ("text-secondary", "bg-surface", 4.5, "Sekundaertext auf Oberflaeche"),
    ("text-muted",     "bg-canvas",  3.0, "gedaempfter Nebentext (bewusst >=3)"),
    ("accent-amber",   "bg-canvas",  4.5, "Bernstein als Text/Aktion"),
    ("brass-bright",   "bg-canvas",  4.5, "Fokus-/Auswahlkante sichtbar"),
    ("brass",          "bg-canvas",  3.0, "Messing-Strukturlinien (Nicht-Text >=3)"),
    ("copper",         "bg-canvas",  3.0, "Kupfer-Interaktion (mit Unterstreichung/Ikonografie)"),
    ("success-moss",   "bg-canvas",  3.0, "Erfolgston"),
    ("warning-ember",  "bg-canvas",  4.5, "Warntext"),
    ("error-brick",    "bg-canvas",  3.0, "Fehlerton (Text-Variante siehe Hinweis)"),
    ("info-copper",    "bg-canvas",  4.5, "Infotext"),
    ("text-primary",   "bg-inset",   7.0, "Haupttext in eingelassenen Flaechen"),
]


def main():
    hexes, rows = {}, []
    for name, L, C, H, zweck in PALETTE:
        hx, c_fit, clipped = to_hex(L, C, H)
        hexes[name] = hx
        note = f" (Chroma auf {c_fit:.3f} reduziert)" if clipped else ""
        rows.append((name, f"oklch({L:.3f} {c_fit:.3f} {H:g})", hx, zweck + note))

    lines = ["| Token | OKLCH | Hex | Zweck |", "|---|---|---|---|"]
    lines += [f"| `--{n}` | `{ok}` | `{hx}` | {z} |" for n, ok, hx, z in rows]

    lines += ["", "### Alpha-Varianten", "", "| Token | Basis | Alpha | Zweck |", "|---|---|---|---|"]
    css_alpha = []
    for name, base, alpha, zweck in ALPHA:
        hx = hexes[base]
        r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
        rgba = f"rgba({r}, {g}, {b}, {alpha})"
        lines.append(f"| `--{name}` | `--{base}` | {alpha} | {zweck} — `{rgba}` |")
        css_alpha.append((name, rgba))

    lines += ["", "### Kontrastpruefung (WCAG)", "", "| Paar | Kontrast | Ziel | Ergebnis |", "|---|---|---|---|"]
    fails = 0
    for fg, bg, minimum, ctx in CHECKS:
        c = contrast(hexes[fg], hexes[bg])
        ok = "OK" if c >= minimum else "**ZU NIEDRIG**"
        fails += 0 if c >= minimum else 1
        lines.append(f"| {fg} auf {bg} | {c:.2f}:1 | >={minimum} | {ok} — {ctx} |")

    with open(os.path.join(OUT_DIR, "palette_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    css = [":root {"]
    css += [f"    --{n}: {hx};  /* {ok} */" for n, ok, hx, _ in rows]
    css += [f"    --{n}: {rgba};" for n, rgba in css_alpha]
    css.append("}")
    with open(os.path.join(OUT_DIR, "palette_root.css"), "w", encoding="utf-8") as f:
        f.write("\n".join(css) + "\n")

    print(f"{len(rows)} Basistoken, {len(ALPHA)} Alpha-Token. Kontrast-Fails: {fails}")
    for fg, bg, minimum, ctx in CHECKS:
        c = contrast(hexes[fg], hexes[bg])
        print(f"  {fg:>14} / {bg:<10} {c:6.2f}:1  (min {minimum})")


if __name__ == "__main__":
    main()
