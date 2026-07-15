# Jarvis — Launch Session (Windows) — Multi-Monitor
# Fehlertolerant: fehlende Apps/Pfade/Monitore werden geloggt und uebersprungen,
# statt den Startfluss abzubrechen.
# -FunctionsOnly laedt nur die Funktionen (Dry-Run/Zonen-Tests) und startet nichts.
param([switch]$FunctionsOnly)

$LogPath = Join-Path $PSScriptRoot "..\jarvis-launch.log"

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    try { Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8 } catch { }
}

Add-Type -AssemblyName System.Windows.Forms
if (-not ([System.Management.Automation.PSTypeName]'WinPos').Type) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinPos {
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int W, int H, bool repaint);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
}

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

# --- Placement-Engine: config-getriebene Fensterplatzierung ------------------
# Nur EXPLIZITE placements aus config.json werden angewendet; Apps ohne
# placement-Feld starten unpositioniert (Default primary/fullscreen ist reine
# UI-Anzeige). left==leftmost, right==rightmost — bewusste Vereinfachung, bei
# zwei Monitoren identisch. Zonen rechnen auf der WorkingArea (Arbeitsbereich
# ohne Taskleiste), nicht auf Bounds.

function Resolve-MonitorArea($monitorKey) {
    $screens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X })
    $primary = [System.Windows.Forms.Screen]::PrimaryScreen
    if ($screens.Count -lt 2) { return $primary.WorkingArea }
    switch ($monitorKey) {
        { $_ -in @('left', 'leftmost') }   { return $screens[0].WorkingArea }
        { $_ -in @('right', 'rightmost') } { return $screens[-1].WorkingArea }
        default                            { return $primary.WorkingArea }  # 'primary' + Unbekanntes
    }
}

function Get-ZoneRect($area, $zone) {
    # x/y/w/h fuer eine Zone. Rechte/untere Haelften bekommen den Rundungsrest,
    # damit bei ungeraden Breiten keine 1px-Luecke entsteht.
    $halfW = [math]::Floor($area.Width / 2)
    $halfH = [math]::Floor($area.Height / 2)
    switch ($zone) {
        'left_half'    { return @{ X = $area.X;          Y = $area.Y;          W = $halfW;               H = $area.Height } }
        'right_half'   { return @{ X = $area.X + $halfW; Y = $area.Y;          W = $area.Width - $halfW; H = $area.Height } }
        'top_half'     { return @{ X = $area.X;          Y = $area.Y;          W = $area.Width;          H = $halfH } }
        'bottom_half'  { return @{ X = $area.X;          Y = $area.Y + $halfH; W = $area.Width;          H = $area.Height - $halfH } }
        'top_left'     { return @{ X = $area.X;          Y = $area.Y;          W = $halfW;               H = $halfH } }
        'top_right'    { return @{ X = $area.X + $halfW; Y = $area.Y;          W = $area.Width - $halfW; H = $halfH } }
        'bottom_left'  { return @{ X = $area.X;          Y = $area.Y + $halfH; W = $halfW;               H = $area.Height - $halfH } }
        'bottom_right' { return @{ X = $area.X + $halfW; Y = $area.Y + $halfH; W = $area.Width - $halfW; H = $area.Height - $halfH } }
        'center'       {
            $w = [math]::Floor($area.Width * 0.70)
            $h = [math]::Floor($area.Height * 0.75)
            return @{ X = $area.X + [math]::Floor(($area.Width - $w) / 2)
                      Y = $area.Y + [math]::Floor(($area.Height - $h) / 2)
                      W = $w; H = $h }
        }
        default        { return @{ X = $area.X; Y = $area.Y; W = $area.Width; H = $area.Height } }  # fullscreen/unbekannt
    }
}

function Get-AppProcessName($entry) {
    # Prozessname zum Fensterfinden: explizites process_name > Ableitung aus
    # command (Spiegel von app_launcher._derive_id_and_name): url -> URL-Schema
    # ('obsidian://open' -> 'obsidian'), sonst Dateiname ohne Pfad/Endung.
    # http/https ohne process_name: kein brauchbarer Kandidat -> $null.
    # Get-Process matcht case-insensitiv ('obsidian' findet 'Obsidian').
    if ($entry.PSObject.Properties['process_name'] -and $entry.process_name) {
        return [string]$entry.process_name
    }
    $cmd = [string]$entry.command
    if ($cmd -match '://') {
        $scheme = ($cmd -split '://', 2)[0]
        if ($scheme -in @('http', 'https')) { return $null }
        return $scheme
    }
    return [System.IO.Path]::GetFileNameWithoutExtension($cmd)
}

function Invoke-PlacementJobs($jobs, $timeoutSec = 15, $pollMs = 500) {
    # Alle offenen Platzierungen im Sammel-Poll: gefundene Fenster werden sofort
    # platziert, der Rest wird bis zum Budget weiter gepollt. Wirft nie.
    if (-not $jobs -or @($jobs).Count -eq 0) {
        Write-Log "INFO: Keine expliziten Platzierungen konfiguriert."
        return
    }
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ($true) {
        foreach ($job in $jobs) {
            if ($job.Done) { continue }
            $proc = Get-Process $job.ProcName -ErrorAction SilentlyContinue |
                Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
            if (-not $proc) { continue }
            try {
                $area = Resolve-MonitorArea $job.Monitor
                if ($job.Zone -eq 'fullscreen') {
                    Set-WindowMaximized $proc $area.X $area.Y $area.Width $area.Height
                } else {
                    $r = Get-ZoneRect $area $job.Zone
                    Set-WindowBounds $proc $r.X $r.Y $r.W $r.H
                }
                Write-Log "INFO: '$($job.Name)' platziert ($($job.Monitor)/$($job.Zone))."
            } catch {
                Write-Log "WARN: '$($job.Name)' konnte nicht platziert werden: $($_.Exception.Message)"
            }
            $job.Done = $true    # auch nach Fehler nicht endlos wiederholen
        }
        $pending = @($jobs | Where-Object { -not $_.Done })
        if ($pending.Count -eq 0) { break }
        if ((Get-Date) -ge $deadline) {
            foreach ($job in $pending) {
                Write-Log "WARN: Fenster fuer '$($job.Name)' (Prozess '$($job.ProcName)') nicht gefunden - Platzierung uebersprungen."
            }
            break
        }
        Start-Sleep -Milliseconds $pollMs
    }
}

# --- Session-Profile (Phase 4) ----------------------------------------------
# Der launcher-Block in config.json bestimmt pro Profil autostart/placement.
# Fehlt er, laeuft der Legacy-Pfad ueber die App-Level-Felder weiter.

function Get-AppKey($app) {
    # Profil-Keys matchen: explizite id > url-Schema > Dateiname (lowercase).
    # Der Server pinnt IDs bei der ersten Mutation — die Ableitung ist nur
    # Best-Effort-Fallback fuer handgepflegte Configs.
    if ($app -isnot [string] -and $app -and $app.PSObject.Properties['id'] -and $app.id) {
        return ([string]$app.id).ToLowerInvariant()
    }
    $cmd = $null
    if ($app -is [string]) { $cmd = $app }
    elseif ($app -and $app.PSObject.Properties['command']) { $cmd = [string]$app.command }
    if (-not $cmd) { return $null }
    if ($cmd -match '://') { return (($cmd -split '://', 2)[0]).ToLowerInvariant() }
    return ([System.IO.Path]::GetFileNameWithoutExtension($cmd)).ToLowerInvariant()
}

function Get-ActiveProfile($config) {
    # Aktives Profil aufloesen; $null = kein launcher-Block -> Legacy-Pfad.
    # Fallback-Kette: active_profile -> Profil 'default' -> erstes Profil.
    if (-not ($config -and $config.PSObject.Properties['launcher'] -and $config.launcher)) { return $null }
    $launcher = $config.launcher
    if (-not ($launcher.PSObject.Properties['profiles'] -and $launcher.profiles)) { return $null }
    $profiles = @($launcher.profiles | Where-Object { $_ -and $_.PSObject.Properties['id'] -and $_.id })
    if ($profiles.Count -eq 0) { return $null }
    $activeId = ''
    if ($launcher.PSObject.Properties['active_profile'] -and $launcher.active_profile) {
        $activeId = ([string]$launcher.active_profile).ToLowerInvariant()
    }
    foreach ($p in $profiles) { if (([string]$p.id).ToLowerInvariant() -eq $activeId) { return $p } }
    foreach ($p in $profiles) { if (([string]$p.id).ToLowerInvariant() -eq 'default') { return $p } }
    return $profiles[0]
}

function Get-AppState($profile, $key) {
    # Effektiver Profil-Zustand einer App. Nicht gelistet = autostart:true,
    # kein Placement (Platzierung nur bei explizitem Profil-Eintrag).
    $state = @{ Autostart = $true; Placement = $null }
    if (-not ($profile -and $key -and $profile.PSObject.Properties['apps'] -and $profile.apps)) { return $state }
    $entry = $null
    foreach ($prop in $profile.apps.PSObject.Properties) {
        if ($prop.Name.ToLowerInvariant() -eq $key) { $entry = $prop.Value; break }
    }
    if (-not $entry) { return $state }
    if ($entry.PSObject.Properties['autostart']) { $state.Autostart = [bool]$entry.autostart }
    if ($entry.PSObject.Properties['placement'] -and $entry.placement) { $state.Placement = $entry.placement }
    return $state
}

# --- Musik (Phase 3/4): Aufloesung + Start der Session-MP3 --------------------
# Get-SelectedMusicPath ist bewusst REIN (kein Logging, keine Seiteneffekte),
# damit sie per -FunctionsOnly end-to-end testbar ist. Sicherheit: gespielt
# wird nur ein REINER .mp3-Dateiname aus music_folder — Pfade/Traversal werden
# verworfen (Spiegel von config_loader.validate_music_file_value).

function Get-SelectedMusicPath($config) {
    # Ergebnis: @{ Path = <voller Pfad oder $null>; Reason = <Begruendung> }.
    if (-not $config) { return @{ Path = $null; Reason = 'keine config.json geladen' } }
    $folder = ''
    $f = ''
    if ($config.PSObject.Properties['music_folder'] -and $config.music_folder) {
        $folder = [string]$config.music_folder
    }
    if ($config.PSObject.Properties['selected_music_file'] -and $config.selected_music_file) {
        $f = ([string]$config.selected_music_file).Trim()
    }
    if (-not $f) { return @{ Path = $null; Reason = 'keine Musik gewaehlt (selected_music_file leer)' } }
    if ([System.IO.Path]::GetFileName($f) -ne $f) {
        return @{ Path = $null; Reason = 'selected_music_file ist kein reiner Dateiname' }
    }
    if (-not $f.ToLowerInvariant().EndsWith('.mp3')) {
        return @{ Path = $null; Reason = 'selected_music_file ist keine .mp3-Datei' }
    }
    if (-not $folder) { return @{ Path = $null; Reason = 'music_folder ist nicht konfiguriert' } }
    $candidate = Join-Path $folder $f
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        return @{ Path = $null; Reason = "Datei nicht gefunden ($candidate)" }
    }
    return @{ Path = $candidate; Reason = 'ok' }
}

function Get-MusicVolume($config) {
    # music_volume invariant parsen (config.json speichert Punkt-Dezimalzahlen)
    # und auf [0,1] klemmen. Fehlt/ungueltig -> Default 0.25.
    $volume = 0.25
    if ($config -and $config.PSObject.Properties['music_volume'] -and "$($config.music_volume)" -ne '') {
        $vol = 0.0
        if ([double]::TryParse("$($config.music_volume)", [System.Globalization.NumberStyles]::Float,
                [System.Globalization.CultureInfo]::InvariantCulture, [ref]$vol)) {
            $volume = [math]::Min([math]::Max($vol, 0.0), 1.0)
        }
    }
    return $volume
}

function Start-BackgroundMusic($path, $volume) {
    # Spielt die MP3 als unsichtbaren PowerShell-Hintergrundprozess (kein
    # Fenster). $null/leerer Pfad = No-Op; Fehler werden geloggt, nie geworfen.
    # Liefert $true, wenn der Abspielprozess gestartet wurde.
    if (-not $path) { return $false }
    try {
        $volStr = ([double]$volume).ToString([System.Globalization.CultureInfo]::InvariantCulture)
        $uriPath = ([string]$path).Replace("'", "''")   # Dateinamen mit ' nicht die Inner-Quotes brechen lassen
        $musicCmd     = "Add-Type -AssemblyName PresentationCore; `$m = [System.Windows.Media.MediaPlayer]::new(); `$m.Open([System.Uri]::new('$uriPath')); `$m.Volume = $volStr; `$m.Play(); Start-Sleep 7200"
        $musicBytes   = [System.Text.Encoding]::Unicode.GetBytes($musicCmd)
        $musicEncoded = [Convert]::ToBase64String($musicBytes)
        Start-Process powershell -ArgumentList "-STA", "-WindowStyle", "Hidden", "-NonInteractive", "-EncodedCommand", $musicEncoded -WindowStyle Hidden
        Write-Log "INFO: Hintergrundmusik gestartet: $(Split-Path $path -Leaf) (Volume $volStr)."
        return $true
    } catch {
        Write-Log "WARN: Hintergrundmusik konnte nicht gestartet werden: $($_.Exception.Message)"
        return $false
    }
}

# --- VS Code aufloesen (rein, -FunctionsOnly-testbar) ------------------------
# Der 'code'-Befehl liegt im PATH als Batch-Shim (...\bin\code.cmd), nicht als
# .exe. Bevorzugt wird Code.exe (direkt startbar, Workspace-Argument sauber
# uebergebbar): erst aus dem Shim abgeleitet, dann die typischen Windows-
# Installationspfade, zuletzt der Shim selbst. $null = VS Code nicht gefunden.
function Resolve-VSCodeCommand {
    $shim = Get-Command code -ErrorAction SilentlyContinue
    if ($shim -and $shim.Source) {
        # ...\Microsoft VS Code\bin\code.cmd  ->  ...\Microsoft VS Code\Code.exe
        $exe = Join-Path (Split-Path (Split-Path $shim.Source -Parent) -Parent) "Code.exe"
        if (Test-Path -LiteralPath $exe) { return $exe }
    }
    $wellKnown = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Microsoft VS Code\Code.exe"),
        (Join-Path $env:ProgramFiles "Microsoft VS Code\Code.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft VS Code\Code.exe")
    )
    foreach ($p in $wellKnown) { if ($p -and (Test-Path -LiteralPath $p)) { return $p } }
    if ($shim -and $shim.Source) { return $shim.Source }
    return $null
}

if ($FunctionsOnly) { return }

# Mini-Rotation: Log-Datei begrenzen, eine Vorgaengerversion behalten.
try {
    if ((Test-Path -LiteralPath $LogPath) -and ((Get-Item -LiteralPath $LogPath).Length -gt 256KB)) {
        Move-Item -LiteralPath $LogPath -Destination "$LogPath.1" -Force
    }
} catch { }

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

# Aktives Session-Profil (Phase 4) — $null = Legacy-Pfad ueber App-Level-Felder.
$activeProfile = Get-ActiveProfile $config
if ($activeProfile) {
    $profName = if ($activeProfile.PSObject.Properties['name'] -and $activeProfile.name) { $activeProfile.name } else { [string]$activeProfile.id }
    Write-Log "INFO: Aktives Profil: '$profName'."
} elseif ($config -and $config.PSObject.Properties['launcher'] -and $config.launcher) {
    Write-Log "WARN: launcher-Block ohne brauchbare Profile - nutze App-Level-Felder."
}

# Monitor-Erkennung: nur noch fuer das Jarvis-Fenster (Apps laufen ueber die
# Placement-Engine / Resolve-MonitorArea).
$allScreens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X })
if ($allScreens.Count -lt 2) {
    Write-Log "INFO: Nur $($allScreens.Count) Monitor erkannt - Fenster werden auf dem vorhandenen Monitor platziert."
}
$right = $allScreens[-1].Bounds

# === START SEQUENCE ===

# 1. Musik — Aufloesung + Start ueber die testbaren Helfer (oben, -FunctionsOnly).
# Ohne gueltige Auswahl startet die Session normal weiter, nur ohne Musik.
$music = Get-SelectedMusicPath $config
if ($music.Path) {
    Start-BackgroundMusic $music.Path (Get-MusicVolume $config) | Out-Null
} else {
    Write-Log "INFO: Musik uebersprungen - $($music.Reason)."
}

# 2. Server + Jarvis-Fenster — werden vom Launcher zusammen gestartet (siehe unten)

# 3. VSCode — startet mit Workspace; der Eintrag mit command 'code' im aktiven
# Profil (bzw. App-Level-Feld im Legacy-Pfad) kann diesen Start deaktivieren.
$vscodeAutostart = $true
if ($config -and $config.apps) {
    foreach ($app in $config.apps) {
        if ($app -isnot [string] -and $app -and $app.PSObject.Properties['command'] -and $app.command -eq 'code') {
            if ($activeProfile) {
                $vscodeAutostart = (Get-AppState $activeProfile (Get-AppKey $app)).Autostart
            } elseif ($app.PSObject.Properties['autostart']) {
                $vscodeAutostart = [bool]$app.autostart
            }
        }
    }
}
Start-Sleep -Seconds 2
if (-not $vscodeAutostart) {
    Write-Log "INFO: VS Code (autostart=false) uebersprungen."
} elseif ($WORKSPACE_PATH -and (Test-Path -LiteralPath $WORKSPACE_PATH)) {
    $vscodeCmd = Resolve-VSCodeCommand
    if (-not $vscodeCmd) {
        Write-Log "WARN: VS Code nicht gefunden ('code' nicht im PATH, keine Standard-Installation) - uebersprungen."
    } else {
        try {
            if ($vscodeCmd.ToLowerInvariant().EndsWith('.exe')) {
                # Code.exe direkt: Workspace als EIN gequotetes Argument (Leerzeichen-sicher).
                Start-Process -FilePath $vscodeCmd -ArgumentList "`"$WORKSPACE_PATH`""
            } else {
                # .cmd-Shim: Call-Operator, Workspace als ein Argument.
                & $vscodeCmd $WORKSPACE_PATH
            }
            Write-Log "INFO: VS Code gestartet ($vscodeCmd) mit Workspace '$WORKSPACE_PATH'."
        } catch {
            Write-Log "WARN: VS Code-Start fehlgeschlagen: $($_.Exception.Message)"
        }
    }
} else {
    Write-Log "WARN: workspace_path fehlt oder existiert nicht - VS Code uebersprungen."
}

# 4. Obsidian + weitere Apps aus config.apps (jede einzeln abgesichert).
# Eintraege sind Strings (Legacy, gelten als autostart) oder Objekte mit
# command/name/autostart — nur autostart-Apps werden beim Sessionstart geoeffnet.
Start-Sleep -Seconds 2
if ($config -and $config.apps) {
    foreach ($app in $config.apps) {
        $cmd = $null; $name = $null; $autostart = $true
        if ($app -is [string]) {
            $cmd = $app; $name = $app
        } elseif ($app -and $app.PSObject.Properties['command']) {
            $cmd = $app.command
            if ($app.PSObject.Properties['name'] -and $app.name) { $name = $app.name } else { $name = $cmd }
            if ($app.PSObject.Properties['autostart']) { $autostart = [bool]$app.autostart }
        }
        if (-not $cmd) { Write-Log "WARN: Ungueltiger apps-Eintrag uebersprungen."; continue }
        # 'code' laeuft bereits ueber Schritt 3 (mit Workspace) bzw. wurde dort bewusst uebersprungen.
        if ($cmd -eq 'code') { continue }
        # Aktives Profil gewinnt ueber App-Level-Felder.
        if ($activeProfile) { $autostart = (Get-AppState $activeProfile (Get-AppKey $app)).Autostart }
        if (-not $autostart) { Write-Log "INFO: App '$name' (autostart=false) uebersprungen."; continue }
        try { Start-Process $cmd } catch { Write-Log "WARN: App '$name' konnte nicht gestartet werden: $($_.Exception.Message)" }
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
$healthUrl = "http://127.0.0.1:8340/health"
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

# === FENSTER POSITIONIEREN (nur explizite placements) ===
# Quelle ist das aktive Profil (Legacy-Pfad: App-Level-Felder). Kein
# 'code'-Skip hier: der VS-Code-Eintrag wird platziert, obwohl Schritt 3 ihn
# gestartet hat. Nicht gestartete Apps (autostart=false) werden nicht angefasst.
$placementJobs = @()
if ($config -and $config.apps) {
    foreach ($app in $config.apps) {
        # Eintrag vereinheitlichen (Strings koennen ueber Profile platziert werden).
        $entry = if ($app -is [string]) { [pscustomobject]@{ command = $app } } else { $app }
        if (-not ($entry -and $entry.PSObject.Properties['command'] -and $entry.command)) { continue }
        $name = if ($entry.PSObject.Properties['name'] -and $entry.name) { $entry.name } else { [string]$entry.command }

        $autostart = $true; $placement = $null
        if ($activeProfile) {
            $state = Get-AppState $activeProfile (Get-AppKey $app)
            $autostart = $state.Autostart
            $placement = $state.Placement
        } else {
            # Legacy: App-Level-Felder; Strings haben nie ein explizites placement.
            if ($app -is [string]) { continue }
            if ($app.PSObject.Properties['autostart']) { $autostart = [bool]$app.autostart }
            if ($app.PSObject.Properties['placement'] -and $app.placement) { $placement = $app.placement }
        }
        if (-not $autostart) { continue }
        if (-not $placement) { continue }
        $procName = Get-AppProcessName $entry
        if (-not $procName) {
            Write-Log "INFO: App '$name' - kein Prozessname bekannt (http/https ohne process_name) - Platzierung uebersprungen."
            continue
        }
        $monitor = 'primary'; $zone = 'fullscreen'                            # Defaults fuer Teil-Objekte
        if ($placement.PSObject.Properties['monitor'] -and $placement.monitor) { $monitor = [string]$placement.monitor }
        if ($placement.PSObject.Properties['zone'] -and $placement.zone) { $zone = [string]$placement.zone }
        $placementJobs += [pscustomobject]@{ Name = $name; ProcName = $procName;
                                             Monitor = $monitor; Zone = $zone; Done = $false }
    }
}
Invoke-PlacementJobs $placementJobs

# Jarvis-Fenster → rechter Monitor, maximiert (kein Registry-Eintrag — bewusst
# hartcodiert und zuletzt, damit Jarvis den Foreground behaelt).
$jarvisProc = Get-Process "pythonw" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*J.A.R.V.I.S*" } |
    Select-Object -First 1
if ($jarvisProc) {
    Set-WindowMaximized $jarvisProc $right.X $right.Y $right.Width $right.Height
} else {
    Write-Log "INFO: Jarvis-Fenster (noch) nicht gefunden - Positionierung uebersprungen."
}
