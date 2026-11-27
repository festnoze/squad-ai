# Gate C gallery: DevShot runs of the release player, several at once, with optional tall windows (MoveWindow past the
# 1200 px monitor). Each config: name|biome|quality|W|H|extra args. Output: <OutRoot>/<name>/.
param(
    [string]$Exe = "C:/Dev/squad-ai/Brainstorming/games/painter_io/Build/Windows/PainterIO.exe",
    [string]$OutRoot = "C:/Dev/squad-ai/Brainstorming/games/painter_io/docs/waveC/shots/final",
    [string[]]$Configs,
    [int]$Parallel = 3,
    [int]$TimeoutSeconds = 300
)
Add-Type -Namespace PioGate -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@ -ErrorAction SilentlyContinue

function Start-Shot([string]$cfg) {
    $parts = $cfg.Split('|')
    $name = $parts[0]; $biome = $parts[1]; $quality = $parts[2]; $W = [int]$parts[3]; $H = [int]$parts[4]
    $extra = if ($parts.Count -gt 5) { $parts[5] } else { "" }
    $dir = Join-Path $OutRoot $name
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    [void](New-Item -ItemType Directory $dir)
    $log = Join-Path $dir "p.log"
    $tall = $H -gt 1150 -or $W -gt 1900
    $sw = if ($tall) { [Math]::Min($W, 540) } else { $W }
    $sh = if ($tall) { [Math]::Min($H, 1100) } else { $H }
    $a = "-devshot `"$dir`" -biome $biome -screen-width $sw -screen-height $sh -screen-fullscreen 0 -logFile `"$log`""
    if ($quality -ne "auto") { $a += " -quality $quality" }
    if ($extra) { $a += " $extra" }
    $p = Start-Process -FilePath $Exe -ArgumentList $a -PassThru
    $null = $p.Handle
    return [pscustomobject]@{ Name = $name; Proc = $p; Tall = $tall; W = $W; H = $H; Moved = $false; Dir = $dir; Start = Get-Date }
}

function Resize-Shot($s) {
    $s.Proc.Refresh()
    $hw = $s.Proc.MainWindowHandle
    if ($hw -eq [System.IntPtr]::Zero) { return }
    $wr = New-Object PioGate.Native+RECT
    $cr = New-Object PioGate.Native+RECT
    [void][PioGate.Native]::GetWindowRect($hw, [ref]$wr)
    [void][PioGate.Native]::GetClientRect($hw, [ref]$cr)
    $bw = ($wr.Right - $wr.Left) - ($cr.Right - $cr.Left)
    $bh = ($wr.Bottom - $wr.Top) - ($cr.Bottom - $cr.Top)
    [void][PioGate.Native]::MoveWindow($hw, 0, -40, $s.W + $bw, $s.H + $bh, $true)
    Start-Sleep -Milliseconds 300
    [void][PioGate.Native]::GetClientRect($hw, [ref]$cr)
    $s.Moved = $true
    "$($s.Name): resized client=$($cr.Right - $cr.Left)x$($cr.Bottom - $cr.Top)"
}

$queue = [System.Collections.Generic.Queue[string]]::new()
foreach ($c in ($Configs -join ";").Split(";")) { if ($c.Trim()) { $queue.Enqueue($c.Trim()) } }
$running = @()
while ($queue.Count -gt 0 -or $running.Count -gt 0) {
    # Tall windows run alone (they cover the screen and must be resized right after the window appears).
    while ($queue.Count -gt 0 -and $running.Count -lt $Parallel) {
        $next = $queue.Peek()
        $p = $next.Split('|')
        $isTall = ([int]$p[4]) -gt 1150 -or ([int]$p[3]) -gt 1900
        if ($isTall -and $running.Count -gt 0) { break }
        if ($running.Count -gt 0 -and ($running | Where-Object { $_.Tall })) { break }
        $running += Start-Shot $queue.Dequeue()
    }
    Start-Sleep -Milliseconds 200
    foreach ($s in $running) {
        if ($s.Tall -and -not $s.Moved -and ((Get-Date) - $s.Start).TotalMilliseconds -gt 500) { Resize-Shot $s }
    }
    $still = @()
    foreach ($s in $running) {
        if ($s.Proc.HasExited) {
            $saved = @(Get-ChildItem $s.Dir -Filter *.png).Count
            $exc = @(Select-String -Path (Join-Path $s.Dir "p.log") -Pattern 'Exception' -ErrorAction SilentlyContinue).Count
            $rs = (Select-String -Path (Join-Path $s.Dir "p.log") -Pattern 'render scale' -ErrorAction SilentlyContinue | Select-Object -First 1).Line
            "$($s.Name): exit=$($s.Proc.ExitCode) pngs=$saved exceptions=$exc $rs"
        }
        elseif (((Get-Date) - $s.Start).TotalSeconds -gt $TimeoutSeconds) { $s.Proc.Kill(); "$($s.Name): TIMEOUT" }
        else { $still += $s }
    }
    $running = $still
}
