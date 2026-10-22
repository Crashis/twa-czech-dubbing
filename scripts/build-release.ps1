param(
    [Parameter(Mandatory = $true)][string]$BasePack,
    [string]$ReferencePack,
    [string]$PythonExecutable,
    [string]$OutputDirectory,
    [switch]$Fast
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExecutable)) { throw 'Create .venv and install requirements-development.txt first.' }
$arguments = @('-B', '-m', 'tools.release', '--base-pack', $BasePack)
if ($ReferencePack) { $arguments += @('--reference-pack', $ReferencePack) }
if ($OutputDirectory) { $arguments += @('--output-directory', $OutputDirectory) }
if ($Fast) { $arguments += '--fast' }
Push-Location -LiteralPath $projectRoot
try {
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE BUILD FAIL. No release is approved. See the build log.' }
} finally { Pop-Location }
