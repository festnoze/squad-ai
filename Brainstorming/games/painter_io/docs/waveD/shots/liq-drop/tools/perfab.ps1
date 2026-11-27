# Interleaved A/B of the liquid per-pixel cost (the perfslope method of tools/verify.ps1, liquid only): release probe
# -quality medium -fps 1000 -mute -biome liquid, windowed 1080 x 1200 and 540 x 600, builds A and B alternated in every
# round, so both builds see the same machine state. Slope = (best avgMs 1080x1200 - best avgMs 540x600) / 0.972 ms/Mpix,
# best over the runs that had the machine to themselves (no other PainterIO.exe, no .unity.lock), all runs as fallback.
param(
    [Parameter(Mandatory = $true)][string]$ExeA,
    [Parameter(Mandatory = $true)][string]$ExeB,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$Rounds = 3
)
$root = "C:/Dev/squad-ai/Brainstorming/games/painter_io"
[void](New-Item -ItemType Directory -Force $OutDir)
# Same serialization as verify.ps1 perfslope: the Logs/perfslope.lock directory with an owner "<pid> <start ticks> <agent>"
# (a dead owner is taken over), and a wait of at most 240 s for a quiet machine before each run.
$lockDir = Join-Path $root "Logs/perfslope.lock"
while ($true) {
    try {
        [void](New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop)
        "$PID $((Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks) liq-drop-perfab" | Out-File (Join-Path $lockDir "owner") -Encoding utf8
        break
    }
    catch { }
    $o = (Get-Content (Join-Path $lockDir "owner") -Raw -ErrorAction SilentlyContinue)
    $op = 0
    if ($o) { [void][int]::TryParse(($o.Trim() -split ' ')[0], [ref]$op) }
    if ($op -gt 0 -and -not (Get-Process -Id $op -ErrorAction SilentlyContinue)) { Remove-Item $lockDir -Recurse -Force -ErrorAction SilentlyContinue; continue }
    [System.Threading.Thread]::Sleep(10000)
}
function Wait-Quiet {
    $until = (Get-Date).AddSeconds(240)
    while (@(Get-Process -Name PainterIO -ErrorAction SilentlyContinue).Count -gt 0 -or (Test-Path "$root/.unity.lock")) {
        if ((Get-Date) -gt $until) { return }
        [System.Threading.Thread]::Sleep(2000)
    }
}
$table = Join-Path $OutDir "perfab.txt"
"build WxH round avgMs p95Ms tier hash shared" | Out-File $table -Encoding utf8
$sizes = @(@{ W = 1080; H = 1200 }, @{ W = 540; H = 600 })
$res = @{}
for ($r = 1; $r -le $Rounds; $r++) {
    foreach ($b in @(@{ N = "A"; E = $ExeA }, @{ N = "B"; E = $ExeB })) {
        foreach ($s in $sizes) {
            $tag = "$($b.N)_$($s.W)x$($s.H)_r$r"
            $dir = Join-Path $OutDir $tag
            [void](New-Item -ItemType Directory -Force $dir)
            $log = Join-Path $dir "player.log"
            Wait-Quiet
            $a = "-probe -shotdir `"$dir`" -fps 1000 -mute -biome liquid -quality medium -screen-width $($s.W) -screen-height $($s.H) -screen-fullscreen 0 -logFile `"$log`""
            $p = Start-Process -FilePath $b.E -ArgumentList $a -PassThru
            $null = $p.Handle
            $shared = $false
            while (-not $p.WaitForExit(1000)) {
                if (@(Get-Process -Name PainterIO -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $p.Id }).Count -gt 0 -or (Test-Path "$root/.unity.lock")) { $shared = $true }
            }
            $perf = (Select-String -Path $log -Pattern '^\[ProbePerf\]' | Select-Object -Last 1).Line
            $hash = ((Select-String -Path $log -Pattern '^\[ProbeHash\] (\S+)' | Select-Object -Last 1).Matches.Groups[1].Value)
            $ms = $null; $p95 = ""; $tier = ""
            if ($perf -match 'avgMs=([0-9.,]+)') { $ms = [double]::Parse($Matches[1].Replace(',', '.'), [Globalization.CultureInfo]::InvariantCulture) }
            if ($perf -match 'p95Ms=([0-9.,]+)') { $p95 = $Matches[1] }
            if ($perf -match 'tier=(\S+)') { $tier = $Matches[1] }
            "$($b.N) $($s.W)x$($s.H) r$r $ms $p95 $tier $hash $shared" | Out-File $table -Append -Encoding utf8
            $key = "$($b.N)|$($s.W)"
            if (-not $res.ContainsKey($key)) { $res[$key] = @{ Quiet = [Collections.Generic.List[double]]::new(); All = [Collections.Generic.List[double]]::new() } }
            if ($null -ne $ms) { $res[$key].All.Add($ms); if (-not $shared) { $res[$key].Quiet.Add($ms) } }
        }
    }
}
foreach ($n in "A", "B") {
    $best = @{}
    foreach ($w in 1080, 540) {
        $k = $res["$n|$w"]
        $set = if ($k.Quiet.Count -gt 0) { $k.Quiet } else { $k.All }
        $best[$w] = ($set | Measure-Object -Minimum).Minimum
    }
    $slope = ($best[1080] - $best[540]) / 0.972
    ("{0}: best avgMs 1080x1200={1:0.00} 540x600={2:0.00} slope={3:0.00} ms/Mpix (quiet runs {4}/{5})" -f $n, $best[1080], $best[540], $slope,
        ($res["$n|1080"].Quiet.Count + $res["$n|540"].Quiet.Count), ($res["$n|1080"].All.Count + $res["$n|540"].All.Count)) | Tee-Object -FilePath $table -Append
}
Remove-Item $lockDir -Recurse -Force -ErrorAction SilentlyContinue
