[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$GamePath,
    [ValidatePattern('^[a-z][a-z0-9_-]*$')][string]$Commander = 'hannibal',
    [switch]$DryRun,
    [string]$PythonExecutable = 'python'
)
. (Join-Path $PSScriptRoot 'common.ps1')
$resolvedGamePath = (Resolve-Path -LiteralPath $GamePath -ErrorAction Stop).Path
$toolArgs = @('restore', '--game-path', $resolvedGamePath, '--commander', $Commander)
if ($DryRun -or -not $PSCmdlet.ShouldProcess($resolvedGamePath, 'Restore canonical original audio_cn.pack')) {
    $toolArgs += '--dry-run'
}
Invoke-DubbingTool -ToolArguments $toolArgs -PythonExecutable $PythonExecutable
