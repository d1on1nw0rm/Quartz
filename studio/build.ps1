$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$root = Split-Path $PSScriptRoot
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    python -m venv .venv
    & $py -m pip install --quiet numpy PySide6==6.12.0 pyinstaller
}
$ico = Join-Path $root 'quartz.ico'
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name Quartz --icon $ico `
    --add-data "$PSScriptRoot\assets;assets" `
    --collect-submodules quartz_studio `
    --exclude-module tkinter --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtPdf --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia `
    --distpath $root --workpath "$env:TEMP\Quartz-build" --specpath "$env:TEMP\Quartz-build" `
    "$PSScriptRoot\launcher.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Write-Host "Done: $root\Quartz.exe"
