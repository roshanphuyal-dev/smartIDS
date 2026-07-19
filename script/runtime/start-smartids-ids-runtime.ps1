param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string]$BackendBaseUrl
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $Root
$env:SMARTIDS_IDS_EVENT_ENDPOINT = "$BackendBaseUrl/api/v1/ids-events"
$env:SMARTIDS_SESSION_UPDATE_ENDPOINT = "$BackendBaseUrl/api/v1/sessions/upsert"
$env:SMARTIDS_BLOCK_EVENT_ENDPOINT = "$BackendBaseUrl/api/v1/block-events/upsert"
$env:SMARTIDS_ENGINE_TELEMETRY_ENDPOINT = "$BackendBaseUrl/api/v1/engine-telemetry"
$env:SMARTIDS_COMMANDS_ENDPOINT = "$BackendBaseUrl/api/v1/engine-commands"
$env:SMARTIDS_COMMANDS_ACK_ENDPOINT = "$BackendBaseUrl/api/v1/engine-commands/ack"

& $PythonExe -m packet_capture.main
