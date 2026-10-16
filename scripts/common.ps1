$ErrorActionPreference = 'Stop'

function Invoke-DubbingTool {
    param([string[]]$ToolArguments, [string]$PythonExecutable = 'python')
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $pythonCommand = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
    $prefixArguments = @()
    if (-not $pythonCommand -and $PythonExecutable -eq 'python') {
        $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
        $prefixArguments = @('-3')
    }
    if (-not $pythonCommand) { throw 'Python 3.11+ is required. Install Python and reopen PowerShell.' }
    & $pythonCommand.Source @prefixArguments -B -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 2)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    Push-Location -LiteralPath $projectRoot
    try {
        & $pythonCommand.Source @prefixArguments -B -m tools.deploy @ToolArguments
        if ($LASTEXITCODE -ne 0) { throw 'Dubbing command failed. Read the ERROR above; no further steps were performed.' }
    } finally {
        Pop-Location
    }
}
