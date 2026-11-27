# Probe run on a tier, then the window is resized past the monitor height with MoveWindow, to see the render scale
# follow Screen.height in the player (the monitor is 1200 px tall, so -screen-height alone is clamped).
param([string]$Exe, [string]$OutDir, [string]$Quality = "low", [int]$W = 760, [int]$H = 1700, [double]$At = 8)
Add-Type -Namespace PioTall -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
[void](New-Item -ItemType Directory $OutDir)
$log = Join-Path $OutDir "p.log"
$p = Start-Process -FilePath $Exe -ArgumentList "-probe -shotdir `"$OutDir`" -fps 60 -mute -biome liquid -quality $Quality -screen-width 720 -screen-height 1200 -screen-fullscreen 0 -logFile `"$log`"" -PassThru
$null = $p.Handle
Start-Sleep -Milliseconds ([int]($At * 1000))
$p.Refresh()
$hw = $p.MainWindowHandle
$ok = [PioTall.Native]::MoveWindow($hw, 0, -300, $W, $H, $true)
Start-Sleep -Seconds 1
$r = New-Object PioTall.Native+RECT
[void][PioTall.Native]::GetClientRect($hw, [ref]$r)
"moved=$ok client=$($r.Right - $r.Left)x$($r.Bottom - $r.Top)"
[void]$p.WaitForExit(300000)
"exit=$($p.ExitCode)"
Select-String -Path $log -Pattern '^\[PainterIO\] render scale|^\[Probe\] actor field|^\[ProbeResult\]|^\[ProbeHash\]|^\[Probe\] shot' | ForEach-Object { $_.Line }
