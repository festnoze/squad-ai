# Electric per-pixel cost, before vs after, like for like (elec-arcs, wave D F3). The same probe runs as the perfslope step
# of tools/verify.ps1 (release probe, -quality medium -fps 1000 -mute, windowed 1080x1200 and 540x600, electric), but for
# two players interleaved round by round (A = before, B = after), so both see the same machine state. Slope = (best
# avgMs 1080x1200 - best avgMs 540x600) / 0.972 ms per Mpix, best = lowest avgMs of the quiet runs (contention only
# adds time). Each run first waits (up to -QuietSeconds) until no other PainterIO.exe runs and no Unity editor holds
# .unity.lock; a run that still shared the machine is retried once and flagged. Serialized with the other agents'
# perfslope runs through Logs/perfslope.lock (same owner format as tools/verify.ps1).
#   pwsh -NoProfile -File docs/waveD/shots/elec-arcs/tools/abperf.ps1 -ExeA Build/Windows/PainterIO.exe -ExeB Build/elec-arcs/PainterIO.exe -Rounds 3 -Out docs/waveD/shots/elec-arcs/perf
param(
    [Parameter(Mandatory = $true)][string]$ExeA,
    [Parameter(Mandatory = $true)][string]$ExeB,
    [int]$Rounds = 3,
    [string]$Out = "docs/waveD/shots/elec-arcs/perf",
    [string]$Biome = "electric",
    [int]$QuietSeconds = 240,
    [int]$TimeoutSeconds = 420
)
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../../../..")).Path
Set-Location $root
New-Item -ItemType Directory -Force $Out | Out-Null
$summary = Join-Path $Out "abperf_$Biome.log"
$lockDir = Join-Path $root "Logs/perfslope.lock"
$unityLock = Join-Path $root ".unity.lock"
"abperf $Biome - $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) - A=$ExeA B=$ExeB rounds=$Rounds" | Out-File $summary -Encoding utf8
function Log([string]$l) { Add-Content -LiteralPath $summary -Value $l -Encoding utf8; $l }

function Get-OtherPlayers([int]$self) { @(Get-Process PainterIO -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $self }) }

function Wait-Quiet([int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-OtherPlayers 0).Count -gt 0 -or (Test-Path -LiteralPath $unityLock)) {
        if ((Get-Date) -gt $deadline) { return $false }
        Start-Sleep -Seconds 2
    }
    return $true
}

function Enter-Lock {
    while ($true) {
        try {
            [void](New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop)
            $me = Get-Process -Id $PID
            "$PID $($me.StartTime.ToUniversalTime().Ticks) elec-arcs-abperf" | Out-File -LiteralPath (Join-Path $lockDir "owner") -Encoding utf8
            return
        }
        catch { }
        $owner = Get-Content -LiteralPath (Join-Path $lockDir "owner") -Raw -ErrorAction SilentlyContinue
        $alive = $true
        if ($owner) {
            $ownerPid = 0
            [void][int]::TryParse(($owner.Trim() -split ' ')[0], [ref]$ownerPid)
            $alive = $ownerPid -gt 0 -and $null -ne (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)
        }
        if (-not $alive) { Remove-Item -LiteralPath $lockDir -Recurse -Force -ErrorAction SilentlyContinue; continue }
        Start-Sleep -Seconds 10
    }
}

function Invoke-Probe([string]$exe, [int]$w, [int]$h, [string]$tag) {
    $dir = Join-Path $root "TestResults/elec-arcs_abperf_$tag"
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    New-Item -ItemType Directory -Force $dir | Out-Null
    $log = Join-Path $dir "player.log"
    $argv = "-probe -shotdir `"$dir`" -fps 1000 -mute -biome $Biome -screen-width $w -screen-height $h -screen-fullscreen 0 -quality medium -logFile `"$log`""
    $p = Start-Process -FilePath (Join-Path $root $exe) -ArgumentList $argv -PassThru
    $null = $p.Handle
    $contended = $false
    $until = (Get-Date).AddSeconds($TimeoutSeconds)
    $done = $false
    while (-not $done -and (Get-Date) -lt $until) {
        if ((Get-OtherPlayers $p.Id).Count -gt 0 -or (Test-Path -LiteralPath $unityLock)) { $contended = $true }
        $done = $p.WaitForExit(1000)
    }
    if (-not $done) { try { $p.Kill($true) } catch { } }
    $text = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
    $ms = $null; $hash = ""; $tier = ""
    if ($text -match '\[ProbePerf\][^\r\n]*avgMs=([0-9.,]+)') { $ms = [double]::Parse($Matches[1].Replace(',', '.'), [Globalization.CultureInfo]::InvariantCulture) }
    if ($text -match '\[ProbePerf\][^\r\n]*tier=(\S+)') { $tier = $Matches[1] }
    if ($text -match '(?m)^\[ProbeHash\] ([0-9A-Fa-f]+)') { $hash = $Matches[1] }
    $ok = $text -match '(?m)^\[ProbeResult\] PASS'
    return [pscustomobject]@{ Ms = $ms; Hash = $hash; Tier = $tier; Ok = $ok; Contended = $contended }
}

Enter-Lock
$best = @{}
$hashes = @{}
try {
    Log "player size round avgMs tier result hash shared"
    for ($r = 1; $r -le $Rounds; $r++) {
        foreach ($size in @(@{ W = 1080; H = 1200; K = "big" }, @{ W = 540; H = 600; K = "small" })) {
            foreach ($pl in @(@{ N = "A"; E = $ExeA }, @{ N = "B"; E = $ExeB })) {
                for ($attempt = 0; $attempt -le 1; $attempt++) {
                    $quiet = Wait-Quiet $QuietSeconds
                    $run = Invoke-Probe $pl.E $size.W $size.H "$($pl.N)_$($size.K)_r$r"
                    $shared = $run.Contended -or -not $quiet
                    Log ("{0} {1}x{2} r{3}{4} {5} {6} {7} {8} {9}" -f $pl.N, $size.W, $size.H, $r, $(if ($attempt) { ".1" } else { "" }),
                        $run.Ms, $run.Tier, $(if ($run.Ok) { "PASS" } else { "FAIL" }), $run.Hash, $shared)
                    if ($run.Hash) { $hashes[$run.Hash] = $true }
                    if ($null -ne $run.Ms -and -not $shared) {
                        $k = "$($pl.N)|$($size.K)"
                        if (-not $best.ContainsKey($k) -or $run.Ms -lt $best[$k]) { $best[$k] = $run.Ms }
                        break
                    }
                }
            }
        }
    }
}
finally { Remove-Item -LiteralPath $lockDir -Recurse -Force -ErrorAction SilentlyContinue }

foreach ($n in "A", "B") {
    if ($best.ContainsKey("$n|big") -and $best.ContainsKey("$n|small")) {
        $slope = ($best["$n|big"] - $best["$n|small"]) / 0.972
        Log ("{0}: best avgMs 1080x1200={1:0.00} 540x600={2:0.00} slope={3:0.00} ms/Mpix" -f $n, $best["$n|big"], $best["$n|small"], $slope)
        Set-Variable -Name "slope$n" -Value $slope
    }
    else { Log "${n}: no complete quiet pair" }
}
if ($slopeA -and $slopeB) { Log ("B vs A: slope {0:+0.0;-0.0} %, 1080x1200 avgMs {1:+0.0;-0.0} %" -f (100 * ($slopeB / $slopeA - 1)), (100 * ($best['B|big'] / $best['A|big'] - 1))) }
Log ("hashes: " + (@($hashes.Keys) -join ', '))
