<#
  garmin-dashboard - Windows setup

  Run once, from a normal PowerShell (not as administrator), in the folder
  where you extracted the project:

      powershell -ExecutionPolicy Bypass -File .\setup.ps1

  What it does:
    1. installs uv (the Python manager) if it is missing
    2. creates a separate Python in %USERPROFILE%\garmin-dashboard with the garminconnect library
    3. logs you in to Garmin Connect (email and password are not stored, only the session tokens)
    4. finds Google Drive for desktop and creates the folder My Drive\garmin-dashboard
    5. runs the first export
    6. schedules the export (every hour from 06:12 to 23:12, and whenever you log on or
       unlock the laptop, with no window; runs closer than 50 minutes apart are skipped)

  Optional parameters:
    -DriveFolder "G:\My Drive"   your Google Drive folder, if it is not found automatically
    -SkipSchedule                 do not schedule the automatic export
#>
param(
    [string]$DriveFolder,
    [switch]$SkipSchedule
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $env:USERPROFILE 'garmin-dashboard'
$venv = Join-Path $app '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
$pyw = Join-Path $venv 'Scripts\pythonw.exe'
$GarminConnectVersion = '0.3.2'

function Step($n, $text) { Write-Host "`n[$n/6] $text" -ForegroundColor Cyan }

# 1. uv
Step 1 'Checking uv'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv...'
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is still missing after the install. Close PowerShell, open it again and rerun setup.ps1.' }

# 2. Python + garminconnect
Step 2 "Preparing Python and garminconnect $GarminConnectVersion in $app"
New-Item -ItemType Directory -Force $app | Out-Null
if (-not (Test-Path $py)) { uv venv --python 3.12 $venv | Out-Host }
uv pip install --python $py "garminconnect==$GarminConnectVersion" | Out-Host
Copy-Item (Join-Path $here 'scripts\garmin_export.py') $app -Force
Copy-Item (Join-Path $here 'scripts\garmin_login.py') $app -Force

# 3. Garmin login
Step 3 'Logging in to Garmin Connect'
& $py (Join-Path $app 'garmin_login.py')
if ($LASTEXITCODE -ne 0) { throw 'The Garmin login failed. Fix the problem shown above and run setup.ps1 again.' }

# 4. Google Drive
Step 4 'Looking for Google Drive for desktop'
if (-not $DriveFolder) {
    $gd = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Description -like '*Google Drive*' } | Select-Object -First 1
    if (-not $gd) { throw 'Google Drive was not found. Install Google Drive for desktop (google.com/drive/download), sign in with the Google account you connect to Claude and run again, or pass the folder with -DriveFolder.' }
    $names = 'My Drive', 'Drive-ul meu', 'Mon Drive', 'Mi unidad', 'Meine Ablage', 'Il mio Drive', 'Mijn Drive', 'Meu Drive'
    $mine = Get-ChildItem $gd.Root -Directory -ErrorAction SilentlyContinue | Where-Object { $names -contains $_.Name } | Select-Object -First 1
    if (-not $mine) { throw "Google Drive is at $($gd.Root), but its My Drive folder was not found. Run again with -DriveFolder ""$($gd.Root)<name of your My Drive folder>""." }
    $DriveFolder = $mine.FullName
}
$out = Join-Path $DriveFolder 'garmin-dashboard'
New-Item -ItemType Directory -Force $out | Out-Null
Write-Host "The files will be written to $out"

# 5. First export
Step 5 'First export (2-3 minutes the first time)'
& $py (Join-Path $app 'garmin_export.py') $out
if ($LASTEXITCODE -ne 0) { throw 'The export failed. See the messages above.' }

# 6. Automatic export
if ($SkipSchedule) {
    Step 6 'Automatic export: skipped (-SkipSchedule)'
} else {
    Step 6 'Scheduling the automatic export'
    $runner = if (Test-Path $pyw) { $pyw } else { $py }
    $log = Join-Path $app 'export.log'
    $arguments = '"{0}" "{1}" --log "{2}" --min-interval 50' -f (Join-Path $app 'garmin_export.py'), $out, $log
    $action = New-ScheduledTaskAction -Execute $runner -Argument $arguments -WorkingDirectory $app
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
    $task = @{ TaskName = 'Garmin dashboard export'; Action = $action; Settings = $settings; Description = 'Exports Garmin data to Google Drive for the Training Log dashboard'; Force = $true }

    # Every hour from 06:12 to 23:12.
    $hourly = New-ScheduledTaskTrigger -Daily -At 06:12
    $hourly.Repetition = (New-ScheduledTaskTrigger -Once -At 06:12 -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 17)).Repetition

    # Also when you log on or unlock the laptop, so a laptop that slept through
    # the hourly runs catches up as soon as you open it.
    $triggers = @($hourly)
    try {
        $me = "$env:USERDOMAIN\$env:USERNAME"
        $logon = New-ScheduledTaskTrigger -AtLogOn -User $me
        $logon.Delay = 'PT2M'
        $unlockClass = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
        $unlock = New-CimInstance -CimClass $unlockClass -ClientOnly
        $unlock.StateChange = 8  # workstation unlock
        $unlock.UserId = $me
        $unlock.Delay = 'PT2M'
        $triggers += $logon, $unlock
    } catch {
        Write-Host "Could not prepare the logon and unlock triggers: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    try {
        Register-ScheduledTask @task -Trigger $triggers | Out-Null
        if ($triggers.Count -gt 1) { Write-Host 'Runs every hour, and when you log on or unlock the laptop.' }
    } catch {
        Write-Host 'Windows did not accept the logon and unlock triggers, so the export runs every hour only.' -ForegroundColor Yellow
        Register-ScheduledTask @task -Trigger $hourly | Out-Null
    }
    $info = Get-ScheduledTaskInfo -TaskName 'Garmin dashboard export'
    Write-Host "Scheduled. Next timed run: $($info.NextRunTime). Log of the last run: $log"
}

Write-Host "`nDone. The next step is in Claude:" -ForegroundColor Green
Write-Host '  1. Connect Google Drive to Claude: claude.ai/customize/connectors'
Write-Host '  2. Open your fork of this repository in claude.ai/code and say: build my Garmin dashboard'
Write-Host '     (details in the README, "The dashboard in Claude")'
