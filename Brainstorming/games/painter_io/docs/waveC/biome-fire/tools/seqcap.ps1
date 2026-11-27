# Records a DevShot run with ffmpeg gdigrab from the DESKTOP (the window DC misses Direct3D content) over the player's
# client area, 12 fps, so the fire fill can be judged as a sequence.
param([string]$Exe, [string]$OutDir, [string]$Quality = "high", [int]$W = 540, [int]$H = 960, [int]$Seconds = 16)
Add-Type -Namespace PioSeqCap -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool ClientToScreen(System.IntPtr h, ref POINT p);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
[DllImport("user32.dll")] public static extern bool SetWindowPos(System.IntPtr h, System.IntPtr after, int x, int y, int cx, int cy, uint flags);
public struct RECT { public int Left, Top, Right, Bottom; }
public struct POINT { public int X, Y; }
'@
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
[void](New-Item -ItemType Directory $OutDir)
$frames = Join-Path $OutDir "frames"
[void](New-Item -ItemType Directory $frames)
$log = Join-Path $OutDir "p.log"
$p = Start-Process -FilePath $Exe -ArgumentList "-devshot `"$OutDir`" -biome fire -quality $Quality -screen-width $W -screen-height $H -screen-fullscreen 0 -logFile `"$log`"" -PassThru
$null = $p.Handle
$t0 = Get-Date
while ($p.MainWindowHandle -eq [System.IntPtr]::Zero -and ((Get-Date) - $t0).TotalSeconds -lt 20) { Start-Sleep -Milliseconds 100; $p.Refresh() }
$hw = $p.MainWindowHandle
$wr = New-Object PioSeqCap.Native+RECT
[void][PioSeqCap.Native]::GetWindowRect($hw, [ref]$wr)
[void][PioSeqCap.Native]::MoveWindow($hw, 100, 0, $wr.Right - $wr.Left, $wr.Bottom - $wr.Top, $true)
[void][PioSeqCap.Native]::SetForegroundWindow($hw)
[void][PioSeqCap.Native]::SetWindowPos($hw, [System.IntPtr](-1), 0, 0, 0, 0, 0x0003)
Start-Sleep -Milliseconds 300
$pt = New-Object PioSeqCap.Native+POINT
[void][PioSeqCap.Native]::ClientToScreen($hw, [ref]$pt)
$cr = New-Object PioSeqCap.Native+RECT
[void][PioSeqCap.Native]::GetClientRect($hw, [ref]$cr)
$cw = $cr.Right - $cr.Left; $ch = $cr.Bottom - $cr.Top
"client at $($pt.X),$($pt.Y) size ${cw}x${ch} after $(((Get-Date) - $t0).TotalSeconds) s"
$ff = Start-Process -FilePath ffmpeg -ArgumentList "-hide_banner -loglevel error -f gdigrab -framerate 12 -draw_mouse 0 -offset_x $($pt.X) -offset_y $($pt.Y) -video_size ${cw}x${ch} -i desktop -t $Seconds `"$frames/f%04d.png`"" -PassThru -NoNewWindow
[void]$p.WaitForExit(240000)
if (-not $ff.HasExited) { [void]$ff.WaitForExit(30000) }
"exit=$($p.ExitCode) frames=$((Get-ChildItem $frames).Count)"
Select-String -Path $log -Pattern '^\[DevShot\] (start|saved)' | ForEach-Object { $_.Line }
