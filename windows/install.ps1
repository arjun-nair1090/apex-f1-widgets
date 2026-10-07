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

# 2. App + widget provider: self-contained build (no .NET install needed), registered in place.
Get-Process -Name APEX -ErrorAction SilentlyContinue | Stop-Process -Force
& $Dotnet build "$PSScriptRoot\APEX" -c Release -p:Platform=x64 -p:RuntimeIdentifier=win-x64 -p:SelfContained=true -v:q -nologo
if ($LASTEXITCODE) { throw "build failed" }
$manifest = Get-ChildItem "$PSScriptRoot\APEX\bin\x64\Release" -Recurse -Filter AppxManifest.xml | Select-Object -First 1
Add-AppxPackage -Register $manifest.FullName

# 3. Let the Widgets board pick up the provider (Windows restarts these on its own).
Get-Process -Name Widgets, WidgetService -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 5
$status = (Invoke-RestMethod http://localhost:8077/api/season/current -TimeoutSec 20)
Write-Host "APEX installed. Data server: season $($status.year), next round $($status.next_round)."
Write-Host "Press Win + W, choose + (Add widgets), and pick APEX."
