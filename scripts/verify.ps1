[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GamePath,
    [ValidatePattern('^[a-z][a-z0-9_-]*$')][string]$Commander = 'hannibal',
    [string]$PythonExecutable = 'python'
)
. (Join-Path $PSScriptRoot 'common.ps1')
$resolvedGamePath = (Resolve-Path -LiteralPath $GamePath -ErrorAction Stop).Path
Invoke-DubbingTool -ToolArguments @('verify', '--game-path', $resolvedGamePath, '--commander', $Commander) -PythonExecutable $PythonExecutable
