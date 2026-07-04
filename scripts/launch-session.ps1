# Jarvis — Launch Session (Windows) — Multi-Monitor
# Fehlertolerant: fehlende Apps/Pfade/Monitore werden geloggt und uebersprungen,
# statt den Startfluss abzubrechen.

$LogPath = Join-Path $PSScriptRoot "..\jarvis-launch.log"

# Mini-Rotation: Log-Datei begrenzen, eine Vorgaengerversion behalten.
try {
    if ((Test-Path -LiteralPath $LogPath) -and ((Get-Item -LiteralPath $LogPath).Length -gt 256KB)) {
        Move-Item -LiteralPath $LogPath -Destination "$LogPath.1" -Force
    }
} catch { }

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    try { Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8 } catch { }
}

# --- Config laden (tolerant) ---
$config = $null
$configPath = Join-Path $PSScriptRoot "..\config.json"
try {
    $config = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Log "WARN: config.json konnte nicht geladen werden ($($_.Exception.Message)). Fahre mit Standardwerten fort."
}

$WORKSPACE_PATH = $null
if ($config -and $config.workspace_path) { $WORKSPACE_PATH = $config.workspace_path }
$MUSIC_PATH = "D:\AI\Musik\Jamtrack inspired by ACDC [No copyright music - Free background music].mp3"

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinPos {
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int W, int H, bool repaint);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

function Set-WindowBounds($proc, $x, $y, $w, $h) {
    if ($proc -and $proc.MainWindowHandle -ne 0) {
        [WinPos]::ShowWindow($proc.MainWindowHandle, 9) | Out-Null
        Start-Sleep -Milliseconds 200
        [WinPos]::MoveWindow($proc.MainWindowHandle, $x, $y, $w, $h, $true) | Out-Null
        [WinPos]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    }
}

function Set-WindowMaximized($proc, $x, $y, $w, $h) {
    if ($proc -and $proc.MainWindowHandle -ne 0) {
        [WinPos]::ShowWindow($proc.MainWindowHandle, 9) | Out-Null
        Start-Sleep -Milliseconds 200
        [WinPos]::MoveWindow($proc.MainWindowHandle, $x, $y, $w, $h, $true) | Out-Null
        Start-Sleep -Milliseconds 100
        [WinPos]::ShowWindow($proc.MainWindowHandle, 3) | Out-Null
        [WinPos]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    }
}

# Monitor-Erkennung: links = kleinster X, rechts = größter X
$allScreens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X })
if ($allScreens.Count -lt 2) {
    Write-Log "INFO: Nur $($allScreens.Count) Monitor erkannt - Fenster werden auf dem vorhandenen Monitor platziert."
}
$left  = $allScreens[0].Bounds
$right = $allScreens[-1].Bounds
$halfLeftW = [math]::Floor($left.Width / 2)

# === START SEQUENCE ===

# 1. Musik — unsichtbarer PowerShell-Hintergrundprozess, kein Fenster (optionaler MP3-Fallback)
if (Test-Path -LiteralPath $MUSIC_PATH) {
    try {
        $musicCmd     = "Add-Type -AssemblyName PresentationCore; `$m = [System.Windows.Media.MediaPlayer]::new(); `$m.Open([System.Uri]::new('$MUSIC_PATH')); `$m.Volume = 0.25; `$m.Play(); Start-Sleep 7200"
        $musicBytes   = [System.Text.Encoding]::Unicode.GetBytes($musicCmd)
        $musicEncoded = [Convert]::ToBase64String($musicBytes)
        Start-Process powershell -ArgumentList "-STA", "-WindowStyle", "Hidden", "-NonInteractive", "-EncodedCommand", $musicEncoded -WindowStyle Hidden
    } catch {
        Write-Log "WARN: Hintergrundmusik konnte nicht gestartet werden: $($_.Exception.Message)"
    }
} else {
    Write-Log "INFO: Keine Hintergrundmusik (MP3 nicht gefunden) - uebersprungen."
}

# 2. Server + Jarvis-Fenster — werden vom Launcher zusammen gestartet (siehe unten)

# 3. VSCode
Start-Sleep -Seconds 2
if ($WORKSPACE_PATH -and (Test-Path -LiteralPath $WORKSPACE_PATH)) {
    if (Get-Command code -ErrorAction SilentlyContinue) {
        try { code $WORKSPACE_PATH } catch { Write-Log "WARN: VS Code-Start fehlgeschlagen: $($_.Exception.Message)" }
    } else {
        Write-Log "WARN: 'code' (VS Code) nicht im PATH - uebersprungen."
    }
} else {
    Write-Log "WARN: workspace_path fehlt oder existiert nicht - VS Code uebersprungen."
}

# 4. Obsidian + weitere Apps aus config.apps (jede einzeln abgesichert)
Start-Sleep -Seconds 2
if ($config -and $config.apps) {
    foreach ($app in $config.apps) {
        try { Start-Process $app } catch { Write-Log "WARN: App '$app' konnte nicht gestartet werden: $($_.Exception.Message)" }
    }
} else {
    Write-Log "INFO: Keine Apps in config.apps konfiguriert - uebersprungen."
}

# 5. Jarvis — nativer pywebview-Launcher (startet Server + Fenster + Tray)
Start-Sleep -Seconds 3
if ($WORKSPACE_PATH) {
    $launcherPath = Join-Path $WORKSPACE_PATH "jarvis-launcher.pyw"
} else {
    $launcherPath = Join-Path $PSScriptRoot "..\jarvis-launcher.pyw"
}
if (Test-Path -LiteralPath $launcherPath) {
    $pythonw = $null
    $pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($pythonExe) {
        $candidate = Join-Path (Split-Path $pythonExe) "pythonw.exe"
        if (Test-Path $candidate) { $pythonw = $candidate }
    }
    if (-not $pythonw -and $pythonExe) { $pythonw = $pythonExe }
    if (-not $pythonw) {
        Write-Log "ERROR: Python nicht gefunden - Jarvis-Launcher kann nicht gestartet werden."
    } else {
        try {
            Start-Process $pythonw -ArgumentList "`"$launcherPath`"" -WorkingDirectory (Split-Path $launcherPath)
        } catch {
            Write-Log "ERROR: Jarvis-Launcher-Start fehlgeschlagen: $($_.Exception.Message)"
        }
    }
} else {
    Write-Log "ERROR: jarvis-launcher.pyw nicht gefunden ($launcherPath) - Jarvis-Fenster wird nicht gestartet."
}

# Warten bis der Server bereit ist (/health antwortet) statt blind zu schlafen.
$healthUrl = "http://localhost:8340/health"
$serverReady = $false
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $serverReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if ($serverReady) {
    Write-Log "INFO: Jarvis-Server bereit (/health ok)."
} else {
    Write-Log "WARN: Jarvis-Server hat nach 30s nicht auf /health geantwortet - fahre trotzdem fort."
}
# Kurz warten, bis das pywebview-Fenster nach Server-Start erscheint.
Start-Sleep -Seconds 2

# === ANDERE FENSTER POSITIONIEREN (null-sicher: fehlende Fenster werden uebersprungen) ===

# VSCode → linke Hälfte des linken Monitors
$vscode = Get-Process "Code" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
Set-WindowBounds $vscode $left.X $left.Y $halfLeftW $left.Height

# Obsidian → rechte Hälfte des linken Monitors
$obsidian = Get-Process "Obsidian" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
Set-WindowBounds $obsidian ($left.X + $halfLeftW) $left.Y $halfLeftW $left.Height

# Jarvis-Fenster → rechter Monitor, maximiert
$jarvisProc = Get-Process "pythonw" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*J.A.R.V.I.S*" } |
    Select-Object -First 1
if ($jarvisProc) {
    Set-WindowMaximized $jarvisProc $right.X $right.Y $right.Width $right.Height
} else {
    Write-Log "INFO: Jarvis-Fenster (noch) nicht gefunden - Positionierung uebersprungen."
}
