# Europe screenshots from a built player (EuropeShot, see Assets/Scripts/Runtime/Probe/EuropeShot.cs).
# Usage: pwsh -NoProfile -File tools/europe_shots.ps1 -Exe Build/europe/PainterIO.exe -Out docs/europe/shots
#        [-Plan map,round] [-Biomes liquid,fire,electric] [-Sizes 540x960,1080x2400] [-Extra "-europe-wins FR,ES"]
# One player run per size and biome; the PNGs land in <Out>/<size>/. Windows taller than the monitor are opened small and
# moved to the wanted client size with MoveWindow right after they appear (the trick of tools/logo/menu_shots.ps1);
# EuropeShot waits until the client size matches (-europeshot-size). No input is ever sent to the window.
param(
    [string]$Exe = "Build/europe/PainterIO.exe",
    [string]$Out = "docs/europe/shots",
    [string]$Plan = "map,round",
    [string[]]$Biomes = @("liquid"),
    [string[]]$Sizes = @("540x960", "1080x2400"),
    [string]$Extra = "",
    [string]$Tag = "",
    [int]$TimeoutSeconds = 150
)
Add-Type -Namespace PioEurope -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@ -ErrorAction SilentlyContinue

$root = Split-Path -Parent $PSScriptRoot
$Biomes = @($Biomes | ForEach-Object { $_.Split(",") } | Where-Object { $_ })
$Sizes = @($Sizes | ForEach-Object { $_.Split(",") } | Where-Object { $_ })
$exePath = (Resolve-Path (Join-Path $root $Exe)).Path
$outRoot = Join-Path $root $Out

function Resize-Client($proc, [int]$w, [int]$h) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 8) {
        $proc.Refresh()
        $hw = $proc.MainWindowHandle
        if ($hw -ne [System.IntPtr]::Zero) {
            $wr = New-Object PioEurope.Native+RECT
            $cr = New-Object PioEurope.Native+RECT
            [void][PioEurope.Native]::GetWindowRect($hw, [ref]$wr)
            [void][PioEurope.Native]::GetClientRect($hw, [ref]$cr)
            $bw = ($wr.Right - $wr.Left) - ($cr.Right - $cr.Left)
            $bh = ($wr.Bottom - $wr.Top) - ($cr.Bottom - $cr.Top)
            [void][PioEurope.Native]::MoveWindow($hw, 0, -40, $w + $bw, $h + $bh, $true)
            return
        }
        Start-Sleep -Milliseconds 100
    }
}

foreach ($size in $Sizes) {
    $w, $h = $size.Split("x")
    $w = [int]$w; $h = [int]$h
    $dir = Join-Path $outRoot $size
    New-Item -ItemType Directory -Force $dir | Out-Null
    foreach ($biome in $Biomes) {
        $log = Join-Path $dir "europeshot_${biome}$Tag.log"
        $tall = $h -gt 1150 -or $w -gt 1900
        $sw = if ($tall) { [Math]::Min($w, 540) } else { $w }
        $sh = if ($tall) { [Math]::Min($h, 1100) } else { $h }
        $argLine = "-europeshot `"$dir`" -europeshot-plan $Plan -europeshot-size ${w}x$h -biome $biome -mute " +
                   "-screen-width $sw -screen-height $sh -screen-fullscreen 0 $Extra -logFile `"$log`""
        $p = Start-Process -FilePath $exePath -ArgumentList $argLine -PassThru
        if ($tall) { Resize-Client $p $w $h }
        if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Write-Output "$size $biome TIMEOUT"
        }
        $saved = @(Select-String -Path $log -Pattern "\[EuropeShot\] saved" -ErrorAction SilentlyContinue).Count
        $doneLine = Select-String -Path $log -Pattern "\[EuropeShot\] done" -ErrorAction SilentlyContinue | Select-Object -First 1
        $errors = @(Select-String -Path $log -Pattern "Exception|\[PainterIO\] .* failed|Shader error|not supported" -ErrorAction SilentlyContinue).Count
        Write-Output ("{0,-10} {1,-9} saved={2} log_errors={3} {4}" -f $size, $biome, $saved, $errors, ($doneLine.Line -replace '^.*\[EuropeShot\] ', ''))
    }
}
