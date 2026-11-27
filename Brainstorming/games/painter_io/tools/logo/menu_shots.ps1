# Menu screenshots of the logo per biome and aspect from a built player (DevShot), stopped once menu.png is written.
# Usage: pwsh -NoProfile -File tools/logo/menu_shots.ps1 -Exe Build/logo/PainterIO.exe -Out docs/waveD/shots/logo/menu
#        [-Biomes liquid,fire,electric] [-Sizes 540x960,1080x2400]
# Windows taller or wider than the monitor are opened small and moved to the wanted client size with MoveWindow right
# after they appear (the trick of docs/waveC/shots/final/tools/shots.ps1), before DevShot's 2 s menu capture.
# A run whose menu shot was not taken in the Menu state (a stray input started a round) is retried once.
param(
    [string]$Exe = "Build/logo/PainterIO.exe",
    [string]$Out = "docs/waveD/shots/logo/menu",
    [string[]]$Biomes = @("liquid", "fire", "electric"),
    [string[]]$Sizes = @("540x960", "1080x2400", "1080x2520", "900x1200", "1280x720"),
    [int]$TimeoutSeconds = 40
)
Add-Type -Namespace PioLogo -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool MoveWindow(System.IntPtr h, int x, int y, int w, int hh, bool repaint);
[DllImport("user32.dll")] public static extern bool GetClientRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@ -ErrorAction SilentlyContinue

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# "-File" passes a comma list as one string: split it.
$Biomes = @($Biomes | ForEach-Object { $_.Split(",") } | Where-Object { $_ })
$Sizes = @($Sizes | ForEach-Object { $_.Split(",") } | Where-Object { $_ })
$exePath = (Resolve-Path (Join-Path $root $Exe)).Path
$outRoot = Join-Path $root $Out

function Resize-Client($proc, [int]$w, [int]$h) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 5) {
        $proc.Refresh()
        $hw = $proc.MainWindowHandle
        if ($hw -ne [System.IntPtr]::Zero) {
            $wr = New-Object PioLogo.Native+RECT
            $cr = New-Object PioLogo.Native+RECT
            [void][PioLogo.Native]::GetWindowRect($hw, [ref]$wr)
            [void][PioLogo.Native]::GetClientRect($hw, [ref]$cr)
            $bw = ($wr.Right - $wr.Left) - ($cr.Right - $cr.Left)
            $bh = ($wr.Bottom - $wr.Top) - ($cr.Bottom - $cr.Top)
            [void][PioLogo.Native]::MoveWindow($hw, 0, -40, $w + $bw, $h + $bh, $true)
            return
        }
        Start-Sleep -Milliseconds 100
    }
}

function Invoke-Shot([string]$biome, [int]$w, [int]$h, [string]$dir) {
    $png = Join-Path $dir "${biome}_menu.png"
    if (Test-Path $png) { Remove-Item $png -Force }
    $log = Join-Path $dir "p.log"
    $tall = $h -gt 1150 -or $w -gt 1900
    $sw = if ($tall) { [Math]::Min($w, 540) } else { $w }
    $sh = if ($tall) { [Math]::Min($h, 1100) } else { $h }
    $argLine = "-devshot `"$dir`" -biome $biome -screen-width $sw -screen-height $sh -screen-fullscreen 0 -logFile `"$log`""
    $p = Start-Process -FilePath $exePath -ArgumentList $argLine -PassThru
    if ($tall) { Resize-Client $p $w $h }
    $t0 = Get-Date
    while (-not (Test-Path $png) -and ((Get-Date) - $t0).TotalSeconds -lt $TimeoutSeconds) { Start-Sleep -Milliseconds 300 }
    Start-Sleep -Milliseconds 800
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    # Keep only the menu shot (the demo round may have started writing other checkpoints).
    Get-ChildItem $dir -Filter *.png | Where-Object { $_.Name -ne "${biome}_menu.png" } | Remove-Item -Force
    $saved = Select-String -Path $log -Pattern "saved ${biome}_menu.png" -ErrorAction SilentlyContinue | Select-Object -First 1
    return [pscustomobject]@{
        Ok = (Test-Path $png)
        InMenu = ($saved -ne $null -and $saved.Line -match "state=Menu")
        Errors = @(Select-String -Path $log -Pattern "Exception|\[PainterIO\] .* failed" -ErrorAction SilentlyContinue).Count
    }
}

foreach ($size in $Sizes) {
    $w, $h = $size.Split("x")
    foreach ($biome in $Biomes) {
        $dir = Join-Path $outRoot "${biome}_$size"
        New-Item -ItemType Directory -Force $dir | Out-Null
        $r = Invoke-Shot $biome ([int]$w) ([int]$h) $dir
        if (-not $r.InMenu) { $r = Invoke-Shot $biome ([int]$w) ([int]$h) $dir }
        Write-Output ("{0,-9} {1,-10} menu={2} inMenu={3} log_errors={4}" -f $biome, $size, $r.Ok, $r.InMenu, $r.Errors)
    }
}
