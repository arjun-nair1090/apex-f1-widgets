# Installs APEX on this PC: builds the app, registers its widgets with the Widgets board (Win+W), and starts the
# data server now and at every logon. Safe to re-run after pulling changes. Needs Developer Mode
# (Settings > System > Advanced > Developer Mode) and Python 3.12+.
#
#   powershell -ExecutionPolicy Bypass -File windows\install.ps1 [-Dotnet <path to dotnet.exe>]
param([string]$Dotnet = "dotnet")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
$backend = Join-Path $root "backend"

# 1. Data server: venv on first run, then a hidden logon task (pythonw + serve.pyw, logs in backend\apex.log).
if (-not (Test-Path "$backend\.venv")) {
    python -m venv "$backend\.venv"
    & "$backend\.venv\Scripts\python.exe" -m pip install -q -r "$backend\requirements.txt"
}
$action = New-ScheduledTaskAction -Execute "$backend\.venv\Scripts\pythonw.exe" -Argument "serve.pyw" -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "APEX backend" -Description "APEX F1 widgets data server on http://localhost:8077" `
    -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName "APEX backend"

# 2. App + widget provider: self-contained build (no .NET install needed). Each install is copied to its own versioned
#    folder and registered as a package update: builds never touch files Windows has open, and pinned widgets survive.
$stage = Join-Path $env:LOCALAPPDATA "APEX\build"  # never the registered folder: Windows memory-maps its resources.pri
& $Dotnet build "$PSScriptRoot\APEX" -c Release -p:Platform=x64 -p:RuntimeIdentifier=win-x64 -p:SelfContained=true `
    "-p:OutDir=$stage\" -v:q -nologo
if ($LASTEXITCODE) { throw "build failed" }
$out = Get-Item $stage
$now = Get-Date
$version = "1.{0}.{1}.0" -f [int]($now - [datetime]"2026-01-01").TotalDays, ($now.Hour * 60 + $now.Minute)
$apps = Join-Path $env:LOCALAPPDATA "APEX\app"
$dest = Join-Path $apps $version
Copy-Item $out.FullName $dest -Recurse -Force
$manifest = Join-Path $dest "AppxManifest.xml"
(Get-Content $manifest -Raw) -replace '(<Identity [^>]*Version=")[^"]+', "`${1}$version" | Set-Content $manifest -Encoding UTF8
Add-AppxPackage -Register $manifest -ForceApplicationShutdown
Get-ChildItem $apps -Directory | Where-Object Name -ne $version |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }  # in-use ones go next time

# 3. Desktop widgets: start at logon (just after the data server) via the package's `apex.exe` alias, and now.
$alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\apex.exe"
$desktopTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$desktopTrigger.Delay = "PT15S"
Register-ScheduledTask -TaskName "APEX desktop widgets" -Description "APEX F1 widgets on the desktop" `
    -Action (New-ScheduledTaskAction -Execute $alias -Argument "-Desktop") -Trigger $desktopTrigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName "APEX desktop widgets"

# 4. Let the Widgets board pick up the provider (Windows restarts these on its own).
Get-Process -Name Widgets, WidgetService -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 5
$status = (Invoke-RestMethod http://localhost:8077/api/season/current -TimeoutSec 20)
Write-Host "APEX installed. Data server: season $($status.year), next round $($status.next_round)."
Write-Host "Desktop widgets are on the right edge of your screen: drag to move, right-click for options."
Write-Host "Widgets board: Win + W, + (Add widgets), APEX. Lock screen: Settings > Personalization > Lock screen > Widgets."
