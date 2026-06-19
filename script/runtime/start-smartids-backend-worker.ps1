param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $Root
& $PythonExe ".\backend\script.py" worker
