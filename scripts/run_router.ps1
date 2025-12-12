param(
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Args
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'py.ps1') '-m' 'agent_v2.scripts.router' @Args
