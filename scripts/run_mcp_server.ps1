param(
  [string] $Host = '127.0.0.1',
  [int] $Port = 8765,
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Extra
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'py.ps1') '-m' 'uvicorn' 'mcp_servers.http_app:app' '--host' $Host '--port' $Port @Extra
