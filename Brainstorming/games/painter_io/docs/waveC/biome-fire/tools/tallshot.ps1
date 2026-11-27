# DevShot in a window taller than the monitor: the player starts at a size the monitor allows, then its window is
# resized with MoveWindow so the client area is exactly W x H (the screen-height argument alone is clamped to 1200).
param([string]$Exe, [string]$OutDir, [string]$Quality = "high", [int]$W = 1080, [int]$H = 2400, [string]$Biome = "fire")
Add-Type -Namespace PioTallShot -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
[void](New-Item -ItemType Directory $OutDir)
$log = Join-Path $OutDir "p.log"
$p = Start-Process -FilePath $Exe -ArgumentList "-devshot `"$OutDir`" -biome $Biome -quality $Quality -screen-width 540 -screen-height 1200 -screen-fullscreen 0 -logFile `"$log`"" -PassThru
$null = $p.Handle
$hw = [System.IntPtr]::Zero
$t0 = Get-Date
while ($hw -eq [System.IntPtr]::Zero -and ((Get-Date) - $t0).TotalSeconds -lt 20) {
    Start-Sleep -Milliseconds 100
    $p.Refresh()
    $hw = $p.MainWindowHandle
}
Start-Sleep -Milliseconds 400
$wr = New-Object PioTallShot.Native+RECT
$cr = New-Object PioTallShot.Native+RECT
[void][PioTallShot.Native]::GetWindowRect($hw, [ref]$wr)
[void][PioTallShot.Native]::GetClientRect($hw, [ref]$cr)
$bw = ($wr.Right - $wr.Left) - ($cr.Right - $cr.Left)
$bh = ($wr.Bottom - $wr.Top) - ($cr.Bottom - $cr.Top)
$ok = [PioTallShot.Native]::MoveWindow($hw, 0, -40, $W + $bw, $H + $bh, $true)
Start-Sleep -Milliseconds 500
[void][PioTallShot.Native]::GetClientRect($hw, [ref]$cr)
"moved=$ok client=$($cr.Right - $cr.Left)x$($cr.Bottom - $cr.Top)"
[void]$p.WaitForExit(240000)
"exit=$($p.ExitCode)"
Select-String -Path $log -Pattern '^\[DevShot\] (start|saved|done)|render scale' | ForEach-Object { $_.Line }
