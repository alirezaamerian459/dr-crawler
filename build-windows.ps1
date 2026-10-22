$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildVenvPython = Join-Path $ProjectDir '.build-venv\Scripts\python.exe'
if (Test-Path -LiteralPath $BuildVenvPython -PathType Leaf) {
    $PythonExecutable = $BuildVenvPython
} else {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $PythonCommand) {
        throw 'Python 3.10 or newer is required on the build computer.'
    }
    $PythonExecutable = $PythonCommand.Source
}

$PythonVersion = & $PythonExecutable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$VersionParts = $PythonVersion.Split('.') | ForEach-Object { [int]$_ }
if (($VersionParts[0] -lt 3) -or (($VersionParts[0] -eq 3) -and ($VersionParts[1] -lt 10))) {
    throw "Python 3.10 or newer is required; found $PythonVersion."
}

Push-Location $ProjectDir
try {
    & $PythonExecutable -m PyInstaller --clean --noconfirm --distpath (Join-Path $ProjectDir 'dist') --workpath (Join-Path $ProjectDir 'build\pyinstaller') (Join-Path $ProjectDir 'drcrawler.spec')
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
    $Result = Join-Path $ProjectDir 'dist\DRCrawler.exe'
    if (-not (Test-Path -LiteralPath $Result -PathType Leaf)) {
        throw 'PyInstaller did not produce dist\DRCrawler.exe.'
    }
    Write-Host "Built $Result"
}
finally {
    Pop-Location
}
