| Token | OKLCH | Hex | Zweck |
|---|---|---|---|
| `--bg-canvas` | `oklch(0.190 0.016 62)` | `#19120c` | Canvas — dunkles Espresso (warm, nicht schwarz) |
| `--bg-surface` | `oklch(0.225 0.018 64)` | `#221a13` | primaere Oberflaeche (Journal, Panels) |
| `--bg-raised` | `oklch(0.265 0.020 66)` | `#2c231b` | erhoehte Oberflaeche (Banner, Chips, Popover) |
| `--bg-inset` | `oklch(0.155 0.014 60)` | `#110b07` | eingelassene Instrumentenflaeche (Map-Bucht, Eingabe, Orb-Bett) |
| `--text-primary` | `oklch(0.900 0.030 84)` | `#e7ddc8` | Haupttext — Pergament |
| `--text-secondary` | `oklch(0.730 0.035 78)` | `#b4a590` | Sekundaertext, Labels |
| `--text-muted` | `oklch(0.565 0.030 72)` | `#817363` | gedaempfter Text (Zeitstempel, Nebeninfo) |
| `--accent-amber` | `oklch(0.775 0.125 72)` | `#e7a854` | Bernstein — Stimme/Leben: Orb, Aktivitaet, Primaeraktion |
| `--accent-amber-deep` | `oklch(0.640 0.125 62)` | `#c17930` | Bernstein tief — pressed/aktive Kante |
| `--brass` | `oklch(0.630 0.065 82)` | `#9d865b` | gealtertes Messing — Struktur, Fassung, ruhige Metallkanten |
| `--brass-bright` | `oklch(0.740 0.085 84)` | `#c4a76b` | helles Messing — Fokusring, Auswahlkante |
| `--copper` | `oklch(0.630 0.105 45)` | `#bd7452` | gedaempftes Kupfer — Sekundaer-Interaktion, Links |
| `--success-moss` | `oklch(0.630 0.075 128)` | `#7c9261` | Erfolg — entsaettigtes Moosgruen |
| `--warning-ember` | `oklch(0.700 0.130 55)` | `#dc8748` | Warnung — gebrannte Glut (zwischen Bernstein und Kupfer) |
| `--error-brick` | `oklch(0.585 0.125 30)` | `#ba5c4e` | Fehler — warmes Ziegelrot |
| `--info-copper` | `oklch(0.680 0.085 48)` | `#c4886a` | Information — helles Kupfer |
| `--orb-idle-core` | `oklch(0.360 0.055 58)` | `#53361f` | Orb idle — glimmende Kohle |
| `--orb-idle-edge` | `oklch(0.170 0.020 58)` | `#160d07` | Orb idle Rand |
| `--orb-listening-core` | `oklch(0.760 0.125 70)` | `#e4a250` | Orb hoert zu — ruhiges Bernstein |
| `--orb-listening-edge` | `oklch(0.340 0.075 58)` | `#542c07` | Orb hoert zu Rand |
| `--orb-thinking-core` | `oklch(0.830 0.125 86)` | `#ebc160` | Orb denkt — helles Arbeitslicht |
| `--orb-thinking-edge` | `oklch(0.420 0.088 78)` | `#674600` | Orb denkt Rand (Chroma auf 0.088 reduziert) |
| `--orb-speaking-core` | `oklch(0.750 0.140 56)` | `#f0944e` | Orb spricht — warmes Sprechlicht |
| `--orb-speaking-edge` | `oklch(0.360 0.090 46)` | `#622b0c` | Orb spricht Rand |
| `--orb-muted-core` | `oklch(0.235 0.020 58)` | `#251c15` | Orb stumm — fast erloschen |
| `--orb-muted-edge` | `oklch(0.140 0.012 58)` | `#0d0805` | Orb stumm Rand |
| `--orb-error-core` | `oklch(0.460 0.120 32)` | `#8f392a` | Orb Fehler — Ziegelglut |
| `--orb-error-edge` | `oklch(0.210 0.050 30)` | `#2b0e0a` | Orb Fehler Rand |
| `--shadow-base` | `oklch(0.100 0.010 60)` | `#050302` | Schattenfarbe (warmes Braunschwarz, per Alpha) |

### Alpha-Varianten

| Token | Basis | Alpha | Zweck |
|---|---|---|---|
| `--border-subtle` | `--brass` | 0.22 | subtile Rahmen/Trennkanten — `rgba(157, 134, 91, 0.22)` |
| `--border-strong` | `--brass-bright` | 0.55 | starke Rahmen (aktive Kante) — `rgba(196, 167, 107, 0.55)` |
| `--edge-light` | `--text-primary` | 0.07 | 1px-Lichtkante oben (gerichtetes Licht) — `rgba(231, 221, 200, 0.07)` |
| `--selection-bg` | `--accent-amber` | 0.14 | Auswahlflaeche (Text-Selektion, aktive Zeile) — `rgba(231, 168, 84, 0.14)` |
| `--focus-halo` | `--brass-bright` | 0.3 | Fokusring-Halo (aussen, zusaetzlich zur 2px-Kante) — `rgba(196, 167, 107, 0.3)` |
| `--glow-amber` | `--accent-amber` | 0.35 | Bernstein-Gluehen (Orb, aktive Dots) — `rgba(231, 168, 84, 0.35)` |
| `--glow-error` | `--error-brick` | 0.35 | Fehler-Gluehen — `rgba(186, 92, 78, 0.35)` |
| `--shadow-soft` | `--shadow-base` | 0.35 | weicher Wurfschatten (erhoehte Flaechen) — `rgba(5, 3, 2, 0.35)` |
| `--shadow-inset` | `--shadow-base` | 0.55 | eingelassener Innenschatten — `rgba(5, 3, 2, 0.55)` |

### Kontrastpruefung (WCAG)

| Paar | Kontrast | Ziel | Ergebnis |
|---|---|---|---|
| text-primary auf bg-canvas | 13.74:1 | >=7.0 | OK — Haupttext auf Canvas (Ziel AAA) |
| text-primary auf bg-surface | 12.71:1 | >=7.0 | OK — Haupttext auf Oberflaeche |
| text-secondary auf bg-canvas | 7.70:1 | >=4.5 | OK — Sekundaertext (AA) |
| text-secondary auf bg-surface | 7.12:1 | >=4.5 | OK — Sekundaertext auf Oberflaeche |
| text-muted auf bg-canvas | 4.03:1 | >=3.0 | OK — gedaempfter Nebentext (bewusst >=3) |
| accent-amber auf bg-canvas | 8.94:1 | >=4.5 | OK — Bernstein als Text/Aktion |
| brass-bright auf bg-canvas | 8.02:1 | >=4.5 | OK — Fokus-/Auswahlkante sichtbar |
| brass auf bg-canvas | 5.29:1 | >=3.0 | OK — Messing-Strukturlinien (Nicht-Text >=3) |
| copper auf bg-canvas | 5.10:1 | >=3.0 | OK — Kupfer-Interaktion (mit Unterstreichung/Ikonografie) |
| success-moss auf bg-canvas | 5.42:1 | >=3.0 | OK — Erfolgston |
| warning-ember auf bg-canvas | 6.71:1 | >=4.5 | OK — Warntext |
| error-brick auf bg-canvas | 4.17:1 | >=3.0 | OK — Fehlerton (Text-Variante siehe Hinweis) |
| info-copper auf bg-canvas | 6.25:1 | >=4.5 | OK — Infotext |
| text-primary auf bg-inset | 14.49:1 | >=7.0 | OK — Haupttext in eingelassenen Flaechen |
