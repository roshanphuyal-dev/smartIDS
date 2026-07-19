param(
    [string]$BaseUrl = "http://127.0.0.1:3100",
    [switch]$HideWindows
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetScript = Join-Path $scriptDir "start-smartids.ps1"

& $targetScript -BaseUrl $BaseUrl -HideWindows:$HideWindows
