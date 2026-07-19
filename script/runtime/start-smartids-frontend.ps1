param(
    [Parameter(Mandatory = $true)]
    [string]$FrontendDir,

    [Parameter(Mandatory = $true)]
    [string]$BackendBaseUrl,

    [Parameter(Mandatory = $true)]
    [int]$BackendPort
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $FrontendDir
$env:NEXT_PUBLIC_IDS_REST_BASE_URL = "$BackendBaseUrl/api/v1"
$env:IDS_REST_BASE_URL = "$BackendBaseUrl/api/v1"
$env:NEXT_PUBLIC_IDS_WS_URL = "ws://127.0.0.1:$BackendPort/api/v1/realtime/ws"

bun run dev -- --port 3000
