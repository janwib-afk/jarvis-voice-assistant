# Jarvis Desktop Launcher — Einmaliges Setup
# Erstellt Desktop-Verknüpfung + optionalen Windows-Autostart

$WORKSPACE = Split-Path $PSScriptRoot -Parent

Write-Host "=== J.A.R.V.I.S. Setup ===" -ForegroundColor Cyan

# ── Icon generieren ──────────────────────────────────────────────────────────
$iconPath = Join-Path $WORKSPACE "assets\jarvis.ico"

$iconScript = @"
from PIL import Image, ImageDraw, ImageFont
import os, sys

sizes = [16, 32, 48, 64, 128]
frames = []
for s in sizes:
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Aeussere Ringe in Bernstein
    pad = max(2, s // 8)
    for i, (a, col) in enumerate([(60, '#3d2210'), (100, '#7a4418'), (160, '#c8922a')]):
        rr = pad + i * max(1, pad // 3)
        d.ellipse([rr, rr, s-rr, s-rr], outline=col, width=max(1, s//32))
    # Gefuellter Kern
    r2 = pad + max(1, pad // 3) * 2
    d.ellipse([r2, r2, s-r2, s-r2], fill='#c8922a', outline='#e8b84b', width=max(1, s//20))
    frames.append(img)

out = sys.argv[1]
os.makedirs(os.path.dirname(out), exist_ok=True)
frames[0].save(out, format='ICO', sizes=[(s,s) for s in sizes], append_images=frames[1:])
print('Icon erstellt: ' + out)
"@

Write-Host "Erstelle Icon..." -ForegroundColor Gray
python -c $iconScript "$iconPath"

if (-not (Test-Path $iconPath)) {
    Write-Warning "Icon konnte nicht erstellt werden. Verknuepfung wird ohne Icon angelegt."
}

# ── pythonw.exe finden ────────────────────────────────────────────────────────
$pythonw = $null
$pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if ($pythonExe) {
    $candidate = Join-Path (Split-Path $pythonExe) "pythonw.exe"
    if (Test-Path $candidate) { $pythonw = $candidate }
}
if (-not $pythonw) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}
if (-not $pythonw) {
    Write-Warning "pythonw.exe nicht gefunden — nutze python.exe (Konsolenfenster sichtbar)"
    $pythonw = $pythonExe
}
Write-Host "Python: $pythonw" -ForegroundColor Gray

$launcher = Join-Path $WORKSPACE "jarvis-launcher.pyw"

# ── Desktop-Verknuepfung ──────────────────────────────────────────────────────
Write-Host "Erstelle Desktop-Verknuepfung..." -ForegroundColor Gray
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "J.A.R.V.I.S..lnk"

$WshShell = New-Object -ComObject WScript.Shell
$lnk = $WshShell.CreateShortcut($lnkPath)
$lnk.TargetPath       = $pythonw
$lnk.Arguments        = "`"$launcher`""
$lnk.WorkingDirectory = $WORKSPACE
$lnk.Description      = "J.A.R.V.I.S. starten"
if (Test-Path $iconPath) { $lnk.IconLocation = "$iconPath,0" }
$lnk.Save()
Write-Host "  Desktop: $lnkPath" -ForegroundColor Green

# ── Windows-Autostart ─────────────────────────────────────────────────────────
$autostart = Read-Host "`nJarvis beim Windows-Start automatisch starten? (j/n)"
if ($autostart -eq "j" -or $autostart -eq "J") {
    $startupFolder = [Environment]::GetFolderPath("Startup")
    $startupLnk = Join-Path $startupFolder "J.A.R.V.I.S..lnk"

    $lnk2 = $WshShell.CreateShortcut($startupLnk)
    $lnk2.TargetPath       = $pythonw
    $lnk2.Arguments        = "`"$launcher`""
    $lnk2.WorkingDirectory = $WORKSPACE
    $lnk2.Description      = "J.A.R.V.I.S. Autostart"
    if (Test-Path $iconPath) { $lnk2.IconLocation = "$iconPath,0" }
    $lnk2.Save()
    Write-Host "  Autostart: $startupLnk" -ForegroundColor Green
} else {
    Write-Host "  Autostart uebersprungen." -ForegroundColor Gray
}

# ── Zusammenfassung ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Fertig!" -ForegroundColor Green
Write-Host "Doppelklick auf den Desktop-Button um Jarvis zu starten." -ForegroundColor White
Write-Host "Hotkey nach dem Start: Win+J (oder Ctrl+Alt+J)" -ForegroundColor White
Write-Host "Tray-Icon: Rechtsklick fuer Menue." -ForegroundColor White
