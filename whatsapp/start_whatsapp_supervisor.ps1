$ErrorActionPreference = "Continue"

$BotDir = "C:\Users\Kmano\Dropbox\Projects\CurrentProject\whatsapp"
$LogDir = Join-Path $BotDir "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class KeepAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

# ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
[KeepAwake]::SetThreadExecutionState(0x80000003) | Out-Null

Set-Location -LiteralPath $BotDir

while ($true) {
    Add-Content -LiteralPath (Join-Path $LogDir "whatsapp-supervisor.log") `
        -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting WhatsApp adapter"

    $process = Start-Process `
        -FilePath "node.exe" `
        -ArgumentList "index.js" `
        -WorkingDirectory $BotDir `
        -RedirectStandardOutput (Join-Path $LogDir "whatsapp-node.out.log") `
        -RedirectStandardError (Join-Path $LogDir "whatsapp-node.err.log") `
        -PassThru `
        -WindowStyle Hidden

    $process.WaitForExit()
    $exitCode = $process.ExitCode

    Add-Content -LiteralPath (Join-Path $LogDir "whatsapp-supervisor.log") `
        -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Node exited with code $exitCode"

    # Exit normally when the adapter intentionally shuts down.
    if ($exitCode -eq 0) {
        break
    }

    # Restart after an unexpected crash.
    Start-Sleep -Seconds 5
}

# Release the keep-awake request.
[KeepAwake]::SetThreadExecutionState(0x80000000) | Out-Null
