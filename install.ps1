# garmin-dashboard installer
#
# Downloads the latest version of this project from GitHub into a temporary
# folder and runs setup.ps1 from it. Run it from a normal PowerShell window:
#
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/alexandrubancioiu/garmin-dashboard/main/install.ps1 | iex"
#
# Running it again later updates the scripts to the latest version; your Garmin
# login and your data are kept.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # makes the download much faster in Windows PowerShell
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $zip = Join-Path $env:TEMP 'garmin-dashboard.zip'
    $dir = Join-Path $env:TEMP 'garmin-dashboard-src'

    Write-Host 'Downloading garmin-dashboard from GitHub...' -ForegroundColor Cyan
    Invoke-WebRequest 'https://github.com/alexandrubancioiu/garmin-dashboard/archive/refs/heads/main.zip' -OutFile $zip -UseBasicParsing
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    Expand-Archive $zip $dir -Force

    $setup = Join-Path $dir 'garmin-dashboard-main\setup.ps1'
    if (-not (Test-Path $setup)) { throw "The download did not contain setup.ps1 ($setup)." }
    powershell -ExecutionPolicy Bypass -File $setup
}
