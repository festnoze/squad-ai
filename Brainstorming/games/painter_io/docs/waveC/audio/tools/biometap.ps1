# Boots the release player windowed on the menu (liquid), then clicks the Feu card, the Electricite card and the Liquide
# card (to restore the saved biome), grabbing a screenshot of the client area after each tap. Verification of robust-03 /
# perf-07: the player log must show both background clip sets ready before the taps and no "clip set built in" line
# after the boot one. PlayerPrefs of the game are snapshotted and restored at the end.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$W = 540,
    [int]$H = 960,
    [int]$BootSeconds = 8,
    [string]$Extra = ""
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class U {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
}
"@
[void][U]::SetProcessDPIAware()
New-Item -ItemType Directory -Force $OutDir | Out-Null

$regPath = 'HKCU:\Software\PainterIO\Painter IO'
$before = @{}
if (Test-Path $regPath) {
    $props = Get-ItemProperty $regPath
    foreach ($pr in $props.PSObject.Properties) { if ($pr.Name -notmatch '^PS') { $before[$pr.Name] = $pr.Value } }
}

$log = Join-Path $OutDir 'p.log'
$argLine = "-screen-width $W -screen-height $H -screen-fullscreen 0 -biome liquid -sfxlog -logFile `"$log`" $Extra"
$p = Start-Process -FilePath $Exe -ArgumentList $argLine -PassThru
$deadline = (Get-Date).AddSeconds(30)
while ($p.MainWindowHandle -eq [IntPtr]::Zero -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200; $p.Refresh() }
$hwnd = $p.MainWindowHandle
"window $hwnd"
# The release player does not run in background (runInBackground false): focus it at once, or it stays paused until the
# first tap. The Alt key press lets this process pass the foreground lock.
for ($try = 0; $try -lt 10 -and [U]::GetForegroundWindow() -ne $hwnd; $try++) {
    [U]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
    [void][U]::ShowWindow($hwnd, 9)
    [void][U]::BringWindowToTop($hwnd)
    [void][U]::SetForegroundWindow($hwnd)
    [U]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 300
}
"focused=$([U]::GetForegroundWindow() -eq $hwnd) t=$((Get-Date).ToString('HH:mm:ss.fff'))"
Start-Sleep -Seconds $BootSeconds
"still focused=$([U]::GetForegroundWindow() -eq $hwnd)"

function Shot([string]$name) {
    $r = New-Object U+RECT
    [void][U]::GetClientRect($hwnd, [ref]$r)
    $pt = New-Object U+POINT
    [void][U]::ClientToScreen($hwnd, [ref]$pt)
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($pt.X, $pt.Y, 0, 0, $bmp.Size)
    $bmp.Save((Join-Path $OutDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
}

function Tap([double]$fx, [double]$fy, [string]$label) {
    $r = New-Object U+RECT
    [void][U]::GetClientRect($hwnd, [ref]$r)
    $pt = New-Object U+POINT
    $pt.X = [int]($fx * ($r.R - $r.L)); $pt.Y = [int]($fy * ($r.B - $r.T))
    [void][U]::ClientToScreen($hwnd, [ref]$pt)
    [void][U]::ShowWindow($hwnd, 9)
    [void][U]::BringWindowToTop($hwnd)
    [void][U]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 300
    [void][U]::SetCursorPos($pt.X, $pt.Y)
    Start-Sleep -Milliseconds 100
    [U]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [U]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    "tap $label at screen $($pt.X),$($pt.Y) (client $([int]($fx * ($r.R - $r.L))),$([int]($fy * ($r.B - $r.T)))) t=$((Get-Date).ToString('HH:mm:ss.fff'))"
}

Shot 'tap0_menu.png'
Tap 0.5 0.40 'Feu'
Start-Sleep -Seconds 3
Shot 'tap1_fire.png'
Tap 0.796 0.40 'Electricite'
Start-Sleep -Seconds 3
Shot 'tap2_electric.png'
Tap 0.204 0.40 'Liquide'
Start-Sleep -Seconds 2
Shot 'tap3_liquid.png'

[void]$p.CloseMainWindow()
if (-not $p.WaitForExit(8000)) { Stop-Process -Id $p.Id -Force }
"exit"

# Restore the game's PlayerPrefs exactly as they were.
if (Test-Path $regPath) {
    $props = Get-ItemProperty $regPath
    foreach ($pr in $props.PSObject.Properties) {
        if ($pr.Name -match '^PS') { continue }
        if (-not $before.ContainsKey($pr.Name)) { Remove-ItemProperty -Path $regPath -Name $pr.Name; "removed pref $($pr.Name)" }
        else { Set-ItemProperty -Path $regPath -Name $pr.Name -Value $before[$pr.Name] }
    }
}
