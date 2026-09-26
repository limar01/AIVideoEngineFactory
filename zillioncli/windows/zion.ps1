# Zillion CLI for Windows (PowerShell Edition)
param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$CommandArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript = Join-Path $ScriptDir "zion_win.py"

if ($CommandArgs.Count -eq 0) {
    Write-Host "⚡ Z I L L I O N   C L I   —   W I N D O W S   E D I T I O N ⚡" -ForegroundColor Cyan
    Write-Host "Usage: zion [send|status|restore|autoheal|me|ls|help] [args...]" -ForegroundColor DarkGray
    & python $PyScript help
} else {
    & python $PyScript $CommandArgs
}
