# Fire probe avgMs per tier at 1080x1200, uncapped (-fps 1000 -mute), interleaved rounds (method of probe_matrix.txt).
param([string]$Exe, [string]$OutRoot, [int]$Rounds = 2, [string[]]$Tiers = @("medium", "low", "high"))
foreach ($r in 1..$Rounds) {
    foreach ($q in $Tiers) {
        $others = @(Get-Process PainterIO -ErrorAction SilentlyContinue).Count
        $unity = @(Get-Process Unity -ErrorAction SilentlyContinue).Count
        $dir = Join-Path $OutRoot "fire_${q}_1080x1200_r$r"
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
        [void](New-Item -ItemType Directory $dir)
        $log = Join-Path $dir "p.log"
        $p = Start-Process -FilePath $Exe -ArgumentList "-probe -shotdir `"$dir`" -fps 1000 -mute -biome fire -quality $q -screen-width 1080 -screen-height 1200 -screen-fullscreen 0 -logFile `"$log`"" -PassThru
        [void]$p.WaitForExit(420000)
        $perf = (Select-String -Path $log -Pattern '^\[ProbePerf\] (.*)$' | Select-Object -Last 1).Matches.Groups[1].Value
        $hash = (Select-String -Path $log -Pattern '^\[ProbeHash\] (.*)$' | Select-Object -Last 1).Matches.Groups[1].Value
        $res = (Select-String -Path $log -Pattern '^\[ProbeResult\] (.*)$' | Select-Object -Last 1).Matches.Groups[1].Value
        "fire $q r$r : $perf | $res $hash | otherPlayersBefore=$others unityBefore=$unity"
    }
}
