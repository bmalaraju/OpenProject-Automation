param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Args)

$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot '..' '.venv' 'Scripts' 'python.exe'
if (-not (Test-Path $py)) {
  Write-Error "Python interpreter not found at $py. Create the venv first (python -m venv .venv) and install requirements (pip install -r requirements.txt)."
  exit 1
}
& $py @Args
