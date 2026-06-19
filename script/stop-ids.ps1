param(
    [switch]$StopDocker
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetScript = Join-Path $scriptDir "stop-smartids.ps1"

& $targetScript -StopDocker:$StopDocker
