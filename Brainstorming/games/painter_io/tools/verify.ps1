# Painter IO verification (contract 18.4). Owned by A1 for the Core steps, extended by B6 for the player steps.
#
# Usage, from the project root with PowerShell 7:
#   pwsh -NoProfile -File tools/verify.ps1                          # every default step, in contract order
#   pwsh -NoProfile -File tools/verify.ps1 -Android -KeepGoing      # the full gate: default steps then the APK, never stop early
#   pwsh -NoProfile -File tools/verify.ps1 -Steps dotnet            # one step
#   pwsh -NoProfile -File tools/verify.ps1 -Steps dotnet,editmode -Agent gateA -KeepGoing
#   pwsh -NoProfile -File tools/verify.ps1 -Steps probe -ProbeExe Build/B6/PainterIO.exe   # probe another build
#   pwsh -NoProfile -File tools/verify.ps1 -List                    # list the known steps
#   pwsh -NoProfile -File tools/verify.ps1 -Steps perfslope -ProbeExe Build/<pkg>/PainterIO.exe -Agent <pkg>   # opt-in
#
# Opt-in step perfslope (wave C, never in the default run): per-pixel shader cost of the three biomes. For liquid, fire
# and electric the release probe runs with -quality medium -fps 1000 -mute windowed at 1080x1200 and at 540x600,
# -PerfRuns (default 2) interleaved rounds; slope = (avgMs at 1080x1200 - avgMs at 540x600) / 0.972 ms per Mpix (the
# best, i.e. lowest, avgMs of the rounds per size: contention only adds time; sizes whose rounds differ by more than
# x1.3 are listed as noisy). The line prints the three slopes and the fire/liquid and electric/liquid ratios, and
# FAILs when fire/liquid > 1.6 or electric/liquid > 1.4 (regression guard; Iris Xe baselines liquid 2.11, electric
# 2.91, fire 4.34 ms per Mpix, docs/waveC/perf/probe_matrix.txt), or when a run fails, reports no [ProbePerf], is not
# on the Medium tier, or the probe hashes differ. Per-run player logs: Logs/<agent>_perfslope_<biome>_<WxH>_r<n>.log;
# the table and the verdict: Logs/<agent>_perfslope.log (written as the runs go, readable while it runs). Runs of
# different agents are serialized by the lock directory Logs/perfslope.lock (two measurements at once would share
# the GPU). Each run first waits (up to 240 s) until no other PainterIO.exe runs and no Unity editor holds
# .unity.lock (on the integrated GPU, CPU load from a build alone slows the frames 2 to 4 times), and a run that
# still shared the machine is measured again (up to 2 retries); only the quiet runs count when a size has one.
# After 30 min the step stops waiting and retrying (the remaining runs go at once), so it always ends. The line says
# how many runs were shared and how many overlapped a Unity editor.
#
# Steps (contract 18.4 order): dotnet (Core tests outside Unity), setup (Builder.SetupAndCompile: settings, scene,
# ShaderCheck), editmode and playmode (Unity tests, JUnit counts, zero tests refused), buildwindows (Build/Windows), probe
# (player probe in the liquid biome at -fps 30 and -fps 144: both PASS, equal [ProbeHash], no exception in the player logs),
# probe-fire and probe-electric (one probe run per biome at -fps 60: PASS, screenshots, no exception, same hash as liquid
# since the Core is identical in every biome), and with -Android the APK build (Build/Android) with the VIBRATE permission
# read back from the APK manifest, always LAST.
#
# Every step prints exactly one line "PASS <step>: <detail>" or "FAIL <step>: <detail>" (or "SKIP <step>: ..." when an
# earlier step failed and -KeepGoing is not set). The exit code is 1 when any step failed, else 0. A summary of the run
# is written to docs/verify_last.txt.
#
# Counting rule (contract 2.1, 19): a test run that executed zero tests is a FAIL, never a PASS. Unity results are read
# from the JUnit report, never from the exit code alone (exit 8 = red tests, any other non-zero = the run did not
# complete). Every Unity call goes through tools/unity.ps1 (exclusive project lock, contract 2.1).
#
# Extending: write a function returning New-StepResult, register it in $StepTable under a lowercase name, and add the
# name to $DefaultSteps in execution order. The Android build only runs with -Android and always as the LAST step.
param(
    [string[]]$Steps,
    [string]$Agent = "verify",
    [int]$MinDotnetTests = 1,
    [int]$MinEditModeTests = 1,
    [int]$MinPlayModeTests = 1,
    [string]$ProbeExe = "Build/Windows/PainterIO.exe",
    [int]$ProbeTimeoutSeconds = 420,
    [int]$PerfRuns = 2,
    [switch]$KeepGoing,
    [switch]$Android,
    [switch]$List
)

# "Continue": stderr lines of dotnet or Unity must never abort the script; every step reports its own failure.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "Logs"
$results = Join-Path $root "TestResults"
foreach ($dir in @($logs, $results)) { if (-not (Test-Path -LiteralPath $dir)) { [void](New-Item -ItemType Directory -Path $dir) } }
$script:LiquidHash = $null

function New-StepResult([bool]$ok, [string]$detail) {
    return [pscustomobject]@{ Ok = $ok; Detail = $detail }
}

function Resolve-ProjectPath([string]$path) {
    if ([System.IO.Path]::IsPathRooted($path)) { return [System.IO.Path]::GetFullPath($path) }
    return [System.IO.Path]::GetFullPath((Join-Path $root $path))
}

# ---------------------------------------------------------------------------------------------------------------------
# Step: dotnet - Core tests outside Unity (contract 2.2), counts read from a TRX report.
# ---------------------------------------------------------------------------------------------------------------------
function Invoke-DotnetStep {
    $project = Join-Path $root "tools/CoreTests/PainterIO.CoreTests.csproj"
    $art = Join-Path $root "tools/CoreTests/.art/$Agent"
    $trxName = "${Agent}_core.trx"
    $trxPath = Join-Path $results $trxName
    $log = Join-Path $logs "${Agent}_dotnet.log"
    Remove-Item -LiteralPath $trxPath -ErrorAction SilentlyContinue

    $output = & dotnet test $project --artifacts-path $art -v q -nologo --results-directory $results --logger "trx;LogFileName=$trxName" 2>&1
    $code = $LASTEXITCODE
    $output | Out-File -LiteralPath $log -Encoding utf8

    if (-not (Test-Path -LiteralPath $trxPath)) {
        return New-StepResult $false "no TRX report (dotnet exit $code; build error?), see Logs/${Agent}_dotnet.log"
    }
    [xml]$trx = Get-Content -LiteralPath $trxPath -Raw
    $c = $trx.TestRun.ResultSummary.Counters
    $total = [int]$c.total
    $passed = [int]$c.passed
    $failed = [int]$c.failed + [int]$c.error + [int]$c.timeout + [int]$c.aborted
    $counts = "total=$total passed=$passed failed=$failed"
    if ($failed -gt 0 -or $code -ne 0) {
        $names = @($trx.TestRun.Results.UnitTestResult | Where-Object { $_.outcome -ne "Passed" -and $_.outcome -ne "NotExecuted" } |
            ForEach-Object { $_.testName } | Select-Object -First 15)
        return New-StepResult $false "$counts exit=$code failing: $($names -join ', ')"
    }
    if ($passed -lt [Math]::Max(1, $MinDotnetTests)) {
        return New-StepResult $false "$counts : refused, fewer than $([Math]::Max(1, $MinDotnetTests)) passing tests"
    }
    return New-StepResult $true $counts
}

# ---------------------------------------------------------------------------------------------------------------------
# Unity test runs through the exclusive lock wrapper (contract 2.1). Shared by editmode and playmode.
# ---------------------------------------------------------------------------------------------------------------------
function Invoke-UnityTests([string]$mode, [string]$suffix, [int]$minTests) {
    $xmlRel = "TestResults/${Agent}_$suffix.xml"
    $xmlPath = Join-Path $root $xmlRel
    $log = Join-Path $logs "${Agent}_$suffix.log"
    Remove-Item -LiteralPath $xmlPath -ErrorAction SilentlyContinue

    $unityArgs = "test . --mode $mode --report-format junit --output $xmlRel --timeout 1800"
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot "unity.ps1") -Agent $Agent -UnityArgs $unityArgs *>&1 |
        Out-File -LiteralPath $log -Encoding utf8
    $code = $LASTEXITCODE

    if (-not (Test-Path -LiteralPath $xmlPath)) {
        return New-StepResult $false "no JUnit report (unity exit $code): the run did not complete, see Logs/${Agent}_$suffix.log"
    }
    [xml]$junit = Get-Content -LiteralPath $xmlPath -Raw
    $suites = $junit.testsuites
    if ($null -eq $suites) { $suites = $junit.testsuite }
    $tests = [int]$suites.tests
    $failures = [int]$suites.failures + [int]$suites.errors
    $skipped = [int]$suites.skipped
    $counts = "tests=$tests failures=$failures skipped=$skipped exit=$code"
    if ($code -ne 0 -and $code -ne 8) {
        return New-StepResult $false "$counts : unity did not complete normally, see Logs/${Agent}_$suffix.log"
    }
    if ($failures -gt 0 -or $code -eq 8) {
        $names = @($junit.SelectNodes("//testcase[failure or error]") | ForEach-Object { "$($_.classname).$($_.name)" } |
            Select-Object -First 15)
        return New-StepResult $false "$counts failing: $($names -join ', ')"
    }
    if ($tests - $skipped -lt [Math]::Max(1, $minTests)) {
        return New-StepResult $false "$counts : refused, fewer than $([Math]::Max(1, $minTests)) executed tests"
    }
    return New-StepResult $true $counts
}

function Invoke-EditModeStep { return Invoke-UnityTests "EditMode" "edit" $MinEditModeTests }
function Invoke-PlayModeStep { return Invoke-UnityTests "PlayMode" "play" $MinPlayModeTests }

# ---------------------------------------------------------------------------------------------------------------------
# Unity editor methods (Builder) through the lock wrapper. $extra goes before -executeMethod (e.g. "-buildTarget Android").
# ---------------------------------------------------------------------------------------------------------------------
function Invoke-UnityMethod([string]$method, [string]$suffix, [int]$timeout, [string]$extra) {
    $logRel = "Logs/${Agent}_$suffix.log"
    $logPath = Join-Path $root $logRel
    $wrapper = Join-Path $logs "${Agent}_${suffix}_cli.log"
    Remove-Item -LiteralPath $logPath -ErrorAction SilentlyContinue
    $unityArgs = "run . --timeout $timeout -- $extra -executeMethod $method -logFile $logRel"
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot "unity.ps1") -Agent $Agent -UnityArgs $unityArgs *>&1 |
        Out-File -LiteralPath $wrapper -Encoding utf8
    $code = $LASTEXITCODE
    $text = if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Raw } else { "" }
    if ($null -eq $text) { $text = "" }
    return [pscustomobject]@{ Code = $code; Log = $logPath; LogRel = $logRel; Text = $text }
}

function Get-FirstMatches([string]$text, [string]$pattern, [int]$count) {
    $found = @([regex]::Matches($text, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline) |
        ForEach-Object { $_.Value.Trim() } | Select-Object -Unique -First $count)
    return ($found -join ' | ')
}

# ---------------------------------------------------------------------------------------------------------------------
# Step: setup - Builder.SetupAndCompile (project settings, Scenes/Main.unity, ShaderCheck). Exit 0 and no compile error.
# ---------------------------------------------------------------------------------------------------------------------
function Invoke-SetupStep {
    $r = Invoke-UnityMethod "PainterIO.Editor.Builder.SetupAndCompile" "setup" 1800 ""
    $compileErrors = ([regex]::Matches($r.Text, '(?m)error CS\d{4}')).Count
    $shaderLine = Get-FirstMatches $r.Text '^\[ShaderCheck\] (PASS|FAIL) Assets/Resources/Shaders.*$' 1
    if ($r.Code -ne 0 -or $compileErrors -gt 0 -or $r.Text -notmatch '\[Builder\] SetupAndCompile PASS') {
        $why = Get-FirstMatches $r.Text '^.*(error CS\d{4}|\[ShaderCheck\] FAIL|\[Builder\].*FAIL).*$' 3
        if (-not $why) { $why = "no '[Builder] SetupAndCompile PASS' line" }
        return New-StepResult $false "exit=$($r.Code) compileErrors=$compileErrors $why (see $($r.LogRel))"
    }
    return New-StepResult $true "exit=0, no compile error, $shaderLine"
}

# ---------------------------------------------------------------------------------------------------------------------
# Step: buildwindows - Builder.BuildWindows into Build/Windows. The exe is copied from the engine with its old date, so
# freshness is judged on the newest file of PainterIO_Data.
# ---------------------------------------------------------------------------------------------------------------------
function Invoke-BuildWindowsStep {
    $exe = Join-Path $root "Build/Windows/PainterIO.exe"
    $data = Join-Path $root "Build/Windows/PainterIO_Data"
    $start = (Get-Date).AddSeconds(-5)
    $r = Invoke-UnityMethod "PainterIO.Editor.Builder.BuildWindows" "buildwindows" 1800 ""
    if ($r.Code -ne 0) {
        $why = Get-FirstMatches $r.Text '^.*(error CS\d{4}|\[Builder\].*(FAIL|fail).*|Build Finished, Result: Failure.*)$' 3
        return New-StepResult $false "exit=$($r.Code) $why (see $($r.LogRel))"
    }
    if (-not (Test-Path -LiteralPath $exe)) { return New-StepResult $false "exit=0 but $exe is missing" }
    $newest = Get-ChildItem -LiteralPath $data -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newest -or $newest.LastWriteTime -lt $start) { return New-StepResult $false "exit=0 but Build/Windows/PainterIO_Data was not rewritten" }
    $mb = [Math]::Round(((Get-ChildItem -LiteralPath (Split-Path $exe) -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    return New-StepResult $true "Build/Windows/PainterIO.exe built ($mb MB)"
}

# ---------------------------------------------------------------------------------------------------------------------
# Player probe runs (contract 18.2). Windowed player, never -batchmode. One run = one shot directory with its player.log.
# ---------------------------------------------------------------------------------------------------------------------
function Format-Arg([string]$a) { if ($a -match '\s') { return '"' + $a + '"' } return $a }

function Get-OtherPlayers([int]$exceptPid) {
    # Every running Painter IO player (any build folder) except $exceptPid.
    return @(Get-Process -Name PainterIO -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $exceptPid })
}

function Invoke-PlayerProbe([string]$label, [int]$fps, [string]$biome, [int]$width = 540, [int]$height = 960,
    [string]$quality = "", [string]$dirName = "", [string]$logPath = "", [bool]$watchOthers = $false) {
    $exe = Resolve-ProjectPath $ProbeExe
    $run = [pscustomobject]@{ Label = $label; Ok = $false; Code = $null; Result = ""; Hash = ""; Perf = ""; Shots = 0;
        Exceptions = @(); Problems = @(); Dir = ""; Log = ""; Contended = $false }
    if (-not (Test-Path -LiteralPath $exe)) { $run.Problems += "no player at $exe (run buildwindows first)"; return $run }
    if (-not $dirName) { $dirName = "${Agent}_probe_$label" }
    $dir = Join-Path $results $dirName
    $run.Dir = $dir
    if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue }
    [void](New-Item -ItemType Directory -Path $dir -Force)
    $log = if ($logPath) { $logPath } else { Join-Path $dir "player.log" }
    $run.Log = $log
    Remove-Item -LiteralPath $log -ErrorAction SilentlyContinue
    $argv = @("-probe", "-shotdir", $dir, "-fps", "$fps", "-mute", "-biome", $biome,
        "-screen-width", "$width", "-screen-height", "$height", "-screen-fullscreen", "0", "-logFile", $log)
    if ($quality) { $argv += @("-quality", $quality) }
    $p = Start-Process -FilePath $exe -ArgumentList (($argv | ForEach-Object { Format-Arg $_ }) -join ' ') -PassThru
    $null = $p.Handle   # keeps the exit code readable after the process ends
    $finished = $false
    if ($watchOthers) {
        # Perf runs: poll once a second and remember whether another player or a Unity editor of this project (its
        # lock) shared the machine meanwhile (on an integrated GPU, CPU load alone slows the frames down 2 to 4 times).
        $until = (Get-Date).AddSeconds($ProbeTimeoutSeconds)
        $unityLockPath = Join-Path $root ".unity.lock"
        while (-not $finished -and (Get-Date) -lt $until) {
            if ((Get-OtherPlayers $p.Id).Count -gt 0 -or (Test-Path -LiteralPath $unityLockPath)) { $run.Contended = $true }
            $finished = $p.WaitForExit(1000)
        }
    }
    else { $finished = $p.WaitForExit($ProbeTimeoutSeconds * 1000) }
    if (-not $finished) {
        try { $p.Kill($true) } catch { }
        $run.Problems += "timeout after $ProbeTimeoutSeconds s (killed)"
    }
    else { $p.WaitForExit() }
    $run.Code = $p.ExitCode
    $text = if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Raw } else { "" }
    if ($null -eq $text) { $text = "" }
    $m = [regex]::Matches($text, '(?m)^\[ProbeResult\] (.*?)\s*$')
    if ($m.Count -gt 0) { $run.Result = $m[$m.Count - 1].Groups[1].Value }
    $m = [regex]::Matches($text, '(?m)^\[ProbeHash\] ([0-9A-Fa-f]+)\s*$')
    if ($m.Count -gt 0) { $run.Hash = $m[$m.Count - 1].Groups[1].Value }
    $m = [regex]::Matches($text, '(?m)^\[ProbePerf\] (.*?)\s*$')
    if ($m.Count -gt 0) { $run.Perf = $m[$m.Count - 1].Groups[1].Value }
    $run.Shots = @(Get-ChildItem -LiteralPath $dir -Filter *.png -File -ErrorAction SilentlyContinue).Count
    # Exceptions, crashes and subsystem failures written by the player itself (the probe's own lines are excluded: they
    # quote what it caught, and its verdict covers them).
    $run.Exceptions = @(($text -split "`r?`n") | Where-Object {
            $_ -notmatch '^\[Probe' -and ($_ -match 'Exception' -or $_ -match 'Crash!!!' -or $_ -match '^\[PainterIO\] .* failed')
        } | Select-Object -First 5)

    if ($run.Result -eq "") { $run.Problems += "no [ProbeResult] line (see $log)" }
    elseif ($run.Result -ne "PASS") { $run.Problems += "[ProbeResult] $($run.Result)" }
    if ($run.Code -ne 0) {
        if ($run.Result -eq "PASS") { $run.Problems += "exit code $($run.Code) after [ProbeResult] PASS (crash at quit?)" }
        elseif ($run.Code -ne 1) { $run.Problems += "exit code $($run.Code)" }
    }
    if ($run.Exceptions.Count -gt 0) { $run.Problems += "player log: $($run.Exceptions -join ' / ')" }
    if ($run.Hash -eq "") { $run.Problems += "no [ProbeHash]" }
    if ($run.Shots -lt 3) { $run.Problems += "only $($run.Shots) screenshots" }
    $run.Ok = $run.Problems.Count -eq 0
    return $run
}

function Format-ProbeRun($run) {
    $state = if ($run.Ok) { "PASS" } else { "FAIL" }
    $text = "$($run.Label) $state exit=$($run.Code) hash=$($run.Hash) shots=$($run.Shots) $($run.Perf)"
    if (-not $run.Ok) { $text += " [" + ($run.Problems -join '; ') + "]" }
    return $text
}

# Step: probe - liquid biome at -fps 30 and -fps 144: both PASS and the same [ProbeHash] (display-rate independence).
function Invoke-ProbeStep {
    $a = Invoke-PlayerProbe "liquid_fps30" 30 "liquid"
    $b = Invoke-PlayerProbe "liquid_fps144" 144 "liquid"
    $ok = $a.Ok -and $b.Ok
    $detail = "$(Format-ProbeRun $a); $(Format-ProbeRun $b)"
    if ($a.Hash -ne "" -and $b.Hash -ne "") {
        if ($a.Hash -eq $b.Hash) { $detail += "; hashes equal"; $script:LiquidHash = $a.Hash }
        else { $ok = $false; $detail += "; HASHES DIFFER" }
    }
    $detail += " (shots in TestResults/${Agent}_probe_liquid_fps30, _fps144)"
    return New-StepResult $ok $detail
}

# Steps: probe-fire, probe-electric - one run per biome: screenshots, checks, no exception, same hash as liquid.
function Invoke-BiomeProbeStep([string]$biome) {
    $r = Invoke-PlayerProbe "${biome}_fps60" 60 $biome
    $ok = $r.Ok
    $detail = Format-ProbeRun $r
    if ($script:LiquidHash -and $r.Hash -ne "") {
        if ($r.Hash -eq $script:LiquidHash) { $detail += "; hash equals liquid" }
        else { $ok = $false; $detail += "; HASH DIFFERS FROM LIQUID ($($script:LiquidHash)): the biome changed the simulation" }
    }
    $detail += " (shots in TestResults/${Agent}_probe_${biome}_fps60)"
    return New-StepResult $ok $detail
}

# ---------------------------------------------------------------------------------------------------------------------
# Step: perfslope (opt-in, wave C perf-01) - per-pixel cost of each biome's shaders, from the release probe's avgMs at two
# window sizes on the Medium tier, uncapped. See the header for the method and the thresholds.
# ---------------------------------------------------------------------------------------------------------------------
$PerfBiomes = @("liquid", "fire", "electric")
$PerfSizes = @(@{ W = 1080; H = 1200; Key = "big" }, @{ W = 540; H = 600; Key = "small" })
$PerfMpix = (1080 * 1200 - 540 * 600) / 1e6   # 0.972
$PerfMaxFireRatio = 1.6
$PerfMaxElectricRatio = 1.4
$PerfLockWaitSeconds = 3600
$PerfQuietWaitSeconds = 240   # per run: wait this long at most for a quiet machine (see Wait-NoOtherPlayer)
$PerfRetries = 2              # a run that shared the machine is measured again up to this many times
$PerfBudgetSeconds = 1800     # past this, no more waiting nor retries: the remaining runs go at once (and are flagged)

function Wait-NoOtherPlayer([int]$seconds) {
    # Waits until no Painter IO player runs (other agents' probes and DevShots last about a minute) and no Unity editor
    # holds this project's lock (builds and tests). True when quiet.
    $deadline = (Get-Date).AddSeconds($seconds)
    $unityLockPath = Join-Path $root ".unity.lock"
    while ((Get-OtherPlayers 0).Count -gt 0 -or (Test-Path -LiteralPath $unityLockPath)) {
        if ((Get-Date) -gt $deadline) { return $false }
        Start-Sleep -Seconds 2
    }
    return $true
}

function Format-Num([double]$v, [string]$fmt = "0.00") { return $v.ToString($fmt, [System.Globalization.CultureInfo]::InvariantCulture) }

function Write-PerfLog([string]$path, [string]$line) {
    try { Add-Content -LiteralPath $path -Value $line -Encoding utf8 } catch { }
}

function Enter-PerfLock([string]$lockDir, [string]$summary) {
    # One perfslope at a time across agents: two measurements at once would share the GPU. The lock is a directory
    # (creation fails when it exists) with an owner file "<pid> <start ticks> <agent>"; a dead owner is taken over.
    $deadline = (Get-Date).AddSeconds($PerfLockWaitSeconds)
    $announced = $false
    while ($true) {
        try {
            [void](New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop)
            $me = Get-Process -Id $PID
            "$PID $($me.StartTime.ToUniversalTime().Ticks) $Agent" | Out-File -LiteralPath (Join-Path $lockDir "owner") -Encoding utf8
            return $true
        }
        catch { }
        $ownerText = Get-Content -LiteralPath (Join-Path $lockDir "owner") -Raw -ErrorAction SilentlyContinue
        $alive = $true
        if ($ownerText) {
            $parts = $ownerText.Trim() -split ' '
            $ownerPid = 0; $ticks = [long]0
            [void][int]::TryParse($parts[0], [ref]$ownerPid)
            if ($parts.Count -gt 1) { [void][long]::TryParse($parts[1], [ref]$ticks) }
            $p = if ($ownerPid -gt 0) { Get-Process -Id $ownerPid -ErrorAction SilentlyContinue } else { $null }
            $alive = $null -ne $p
            if ($alive -and $ticks -gt 0) {
                try { $alive = [math]::Abs($p.StartTime.ToUniversalTime().Ticks - $ticks) -lt 20000000 } catch { }
            }
        }
        else {
            # No owner yet: fresh lock being written, or a crash between the two writes (judged on the directory age).
            $d = Get-Item -LiteralPath $lockDir -Force -ErrorAction SilentlyContinue
            $alive = $d -and ((Get-Date) - $d.LastWriteTime).TotalSeconds -lt 60
        }
        if (-not $alive) {
            Remove-Item -LiteralPath $lockDir -Recurse -Force -ErrorAction SilentlyContinue
            Write-PerfLog $summary "took over a stale perfslope lock: '$ownerText'"
            continue
        }
        if (-not $announced) { Write-PerfLog $summary "waiting for the perfslope lock held by: '$(("$ownerText").Trim())'"; $announced = $true }
        if ((Get-Date) -gt $deadline) { return $false }
        Start-Sleep -Seconds 10
    }
}

function Invoke-PerfSlopeStep {
    $summary = Join-Path $logs "${Agent}_perfslope.log"
    $lockDir = Join-Path $logs "perfslope.lock"
    $unityLock = Join-Path $root ".unity.lock"
    $exe = Resolve-ProjectPath $ProbeExe
    "Painter IO perfslope - $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) - agent $Agent - player $exe - runs $PerfRuns" |
        Out-File -LiteralPath $summary -Encoding utf8
    if (-not (Test-Path -LiteralPath $exe)) { return New-StepResult $false "no player at $exe (run buildwindows first)" }
    if ($PerfRuns -lt 1) { return New-StepResult $false "-PerfRuns must be at least 1" }
    if (-not (Enter-PerfLock $lockDir $summary)) {
        return New-StepResult $false "another perfslope held Logs/perfslope.lock for over $PerfLockWaitSeconds s"
    }
    $problems = [System.Collections.Generic.List[string]]::new()
    $avg = @{}       # "<biome>|<size>" -> avgMs of the runs that had the machine to themselves
    $avgAll = @{}    # same, every run (used only when no quiet run exists for that size)
    $hashes = @{}
    $busy = 0
    $total = 0
    $contended = 0
    $perfStart = Get-Date
    try {
        Write-PerfLog $summary "biome tier WxH run avgMs p95Ms result hash unityBusy otherPlayer"
        for ($r = 1; $r -le $PerfRuns; $r++) {
            foreach ($biome in $PerfBiomes) {
                foreach ($size in $PerfSizes) {
                    $key = "$biome|$($size.Key)"
                    foreach ($set in @($avg, $avgAll)) { if (-not $set.ContainsKey($key)) { $set[$key] = [System.Collections.Generic.List[double]]::new() } }
                    for ($attempt = 0; $attempt -le $PerfRetries; $attempt++) {
                        $tag = "${biome}_$($size.W)x$($size.H)_r$r" + $(if ($attempt -gt 0) { "_retry$attempt" } else { "" })
                        $overBudget = ((Get-Date) - $perfStart).TotalSeconds -gt $PerfBudgetSeconds
                        if ($overBudget -and $attempt -gt 0) { break }
                        $quiet = Wait-NoOtherPlayer $(if ($overBudget) { 0 } else { $PerfQuietWaitSeconds })
                        $busyBefore = Test-Path -LiteralPath $unityLock
                        $run = Invoke-PlayerProbe "perf_$tag" 1000 $biome $size.W $size.H "medium" "${Agent}_perfslope_$tag" (Join-Path $logs "${Agent}_perfslope_$tag.log") $true
                        $busyRun = $busyBefore -or (Test-Path -LiteralPath $unityLock)
                        $shared = $run.Contended -or -not $quiet
                        $total++
                        if ($busyRun) { $busy++ }
                        if ($shared) { $contended++ }
                        $ms = $null; $p95 = ""; $tier = ""
                        if ($run.Perf -match 'avgMs=([0-9.,]+)') { $ms = [double]::Parse($Matches[1].Replace(',', '.'), [System.Globalization.CultureInfo]::InvariantCulture) }
                        if ($run.Perf -match 'p95Ms=([0-9.,]+)') { $p95 = $Matches[1] }
                        if ($run.Perf -match 'tier=(\S+)') { $tier = $Matches[1] }
                        $state = if ($run.Ok) { "PASS" } else { "FAIL" }
                        $msText = if ($null -ne $ms) { Format-Num $ms } else { "?" }
                        Write-PerfLog $summary "$biome $tier $($size.W)x$($size.H) r$r$(if ($attempt -gt 0) { ".$attempt" }) $msText $p95 $state $($run.Hash) $busyRun $shared"
                        if (-not $run.Ok) { $problems.Add("$tag probe FAIL [$($run.Problems -join '; ')]") }
                        if ($null -eq $ms) { $problems.Add("$tag no [ProbePerf] avgMs"); break }
                        if ($tier -ne "Medium") { $problems.Add("$tag tier=$tier, not Medium") }
                        if ($run.Hash) { $hashes[$run.Hash] = $true }
                        $avgAll[$key].Add($ms)
                        if (-not $shared) { $avg[$key].Add($ms); break }
                    }
                }
            }
        }
    }
    finally {
        Remove-Item -LiteralPath $lockDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    $slope = @{}
    $parts = @()
    $noisy = [System.Collections.Generic.List[string]]::new()
    foreach ($biome in $PerfBiomes) {
        $big = $avg["$biome|big"]; $small = $avg["$biome|small"]
        # A size with no quiet run falls back to every run (and says so): an estimate is better than none.
        if ((-not $big -or $big.Count -eq 0) -and $avgAll["$biome|big"] -and $avgAll["$biome|big"].Count -gt 0) {
            $big = $avgAll["$biome|big"]; $noisy.Add("$biome 1080x1200 never quiet")
        }
        if ((-not $small -or $small.Count -eq 0) -and $avgAll["$biome|small"] -and $avgAll["$biome|small"].Count -gt 0) {
            $small = $avgAll["$biome|small"]; $noisy.Add("$biome 540x600 never quiet")
        }
        if (-not $big -or -not $small -or $big.Count -eq 0 -or $small.Count -eq 0) {
            $problems.Add("$biome has no complete pair of sizes")
            $parts += "$biome=?"
            continue
        }
        # Best of the rounds per size: contention (a Unity editor compiling, another player on the GPU) only ever adds
        # time, so the minimum is the least noisy estimate of the run's own cost.
        $mBig = ($big | Measure-Object -Minimum).Minimum
        $mSmall = ($small | Measure-Object -Minimum).Minimum
        $slope[$biome] = ($mBig - $mSmall) / $PerfMpix
        $parts += "$biome=$(Format-Num $slope[$biome])"
        foreach ($set in @(@{ V = $big; S = "1080x1200" }, @{ V = $small; S = "540x600" })) {
            $hi = ($set.V | Measure-Object -Maximum).Maximum
            $lo = ($set.V | Measure-Object -Minimum).Minimum
            if ($lo -gt 0 -and $hi / $lo -gt 1.3) { $noisy.Add("$biome $($set.S) x$(Format-Num ($hi / $lo) '0.0')") }
        }
        Write-PerfLog $summary "$biome best avgMs 1080x1200=$(Format-Num $mBig) 540x600=$(Format-Num $mSmall) slope=$(Format-Num $slope[$biome]) ms/Mpix"
    }
    $detail = "slopes ms/Mpix (medium, uncapped) " + ($parts -join ' ')
    if ($slope.ContainsKey("liquid") -and $slope["liquid"] -gt 0.05) {
        foreach ($pair in @(@{ B = "fire"; Max = $PerfMaxFireRatio }, @{ B = "electric"; Max = $PerfMaxElectricRatio })) {
            if (-not $slope.ContainsKey($pair.B)) { continue }
            $ratio = $slope[$pair.B] / $slope["liquid"]
            $detail += "; $($pair.B)/liquid=$(Format-Num $ratio) (max $(Format-Num $pair.Max '0.0'))"
            if ($ratio -gt $pair.Max) { $problems.Add("$($pair.B)/liquid $(Format-Num $ratio) > $(Format-Num $pair.Max '0.0')") }
        }
    }
    elseif ($slope.ContainsKey("liquid")) { $problems.Add("liquid slope $(Format-Num $slope['liquid']) is not positive: no ratio") }
    if ($hashes.Count -gt 1) { $problems.Add("PROBE HASHES DIFFER: $(@($hashes.Keys) -join ', ')") }
    elseif ($hashes.Count -eq 1) { $detail += "; hash $(@($hashes.Keys)[0])" }
    $detail += "; $total runs ($contended shared the machine with another player or a Unity editor, $busy of them with a Unity editor)"
    if ($noisy.Count -gt 0) { $detail += "; noisy (max/min of the rounds > 1.3): $($noisy -join ', ')" }
    if ($problems.Count -gt 0) { $detail += " [" + ($problems -join '; ') + "]" }
    $detail += " (table in Logs/${Agent}_perfslope.log)"
    $ok = $problems.Count -eq 0
    Write-PerfLog $summary ("{0} perfslope: {1}" -f $(if ($ok) { "PASS" } else { "FAIL" }), $detail)
    return New-StepResult $ok $detail
}

# ---------------------------------------------------------------------------------------------------------------------
# Step: android - Builder.BuildAndroid started with -buildTarget Android (so the VIBRATE Gradle callback is compiled in),
# APK into Build/Android, then android.permission.VIBRATE read back from the APK's merged binary manifest.
# ---------------------------------------------------------------------------------------------------------------------
function Test-ApkPermission([string]$apk, [string]$permission) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($apk)
    try {
        $entry = $zip.GetEntry("AndroidManifest.xml")
        if (-not $entry) { return $null }
        $stream = $entry.Open()
        $ms = [System.IO.MemoryStream]::new()
        try { $stream.CopyTo($ms) } finally { $stream.Dispose() }
        $bytes = $ms.ToArray()
        # Binary XML string pools are UTF-16LE (or UTF-8 when flagged): look for both encodings.
        $u16 = [System.Text.Encoding]::Unicode.GetString($bytes)
        $u16odd = if ($bytes.Length -gt 1) { [System.Text.Encoding]::Unicode.GetString($bytes, 1, $bytes.Length - 1) } else { "" }
        $u8 = [System.Text.Encoding]::UTF8.GetString($bytes)
        return ($u16.Contains($permission) -or $u16odd.Contains($permission) -or $u8.Contains($permission))
    }
    finally { $zip.Dispose() }
}

function Invoke-AndroidStep {
    $apk = Join-Path $root "Build/Android/PainterIO.apk"
    $start = (Get-Date).AddSeconds(-5)
    $r = Invoke-UnityMethod "PainterIO.Editor.Builder.BuildAndroid" "android" 3600 "-buildTarget Android"
    if ($r.Code -ne 0) {
        $why = Get-FirstMatches $r.Text '^.*(error CS\d{4}|\[Builder\].*(FAIL|fail).*|Build Finished, Result: Failure.*|FAILURE: .*)$' 3
        return New-StepResult $false "exit=$($r.Code) $why (see $($r.LogRel))"
    }
    if (-not (Test-Path -LiteralPath $apk)) { return New-StepResult $false "exit=0 but $apk is missing" }
    $file = Get-Item -LiteralPath $apk
    if ($file.LastWriteTime -lt $start) { return New-StepResult $false "exit=0 but the APK is older than this run" }
    $permission = "android.permission.VIBRATE"
    $has = $null
    try { $has = Test-ApkPermission $apk $permission } catch { $has = $null }
    if ($null -eq $has) { return New-StepResult $false "APK built but its AndroidManifest.xml could not be read" }
    if (-not $has) { return New-StepResult $false "APK built but $permission is missing from its manifest" }
    $mb = [Math]::Round($file.Length / 1MB, 1)
    return New-StepResult $true "Build/Android/PainterIO.apk ($mb MB), $permission present in the APK manifest"
}

# ---------------------------------------------------------------------------------------------------------------------
# Step registry. Order of $DefaultSteps = execution order (contract 18.4).
# ---------------------------------------------------------------------------------------------------------------------
$StepTable = [ordered]@{
    "dotnet"         = { Invoke-DotnetStep }
    "setup"          = { Invoke-SetupStep }
    "editmode"       = { Invoke-EditModeStep }
    "playmode"       = { Invoke-PlayModeStep }
    "buildwindows"   = { Invoke-BuildWindowsStep }
    "probe"          = { Invoke-ProbeStep }
    "probe-fire"     = { Invoke-BiomeProbeStep "fire" }
    "probe-electric" = { Invoke-BiomeProbeStep "electric" }
    "perfslope"      = { Invoke-PerfSlopeStep }
    "android"        = { Invoke-AndroidStep }
}
# perfslope is opt-in (about 10 minutes of measurement): registered above, never in the default run.
$DefaultSteps = @("dotnet", "setup", "editmode", "playmode", "buildwindows", "probe", "probe-fire", "probe-electric")
$AndroidStep = "android"   # appended last when -Android is given (or when named in -Steps)

if ($List) {
    "Known steps: $(@($StepTable.Keys) -join ', ')"
    "Default order: $($DefaultSteps -join ', ') (then $AndroidStep with -Android; perfslope only when named in -Steps)"
    exit 0
}

# "-Steps a,b" arrives as one string through "pwsh -File": split on commas.
if (-not $Steps -or $Steps.Count -eq 0) { $Steps = $DefaultSteps }
$Steps = @($Steps | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
# The Android build is always the LAST step.
$wantAndroid = $Android -or ($Steps -contains $AndroidStep)
$Steps = @($Steps | Where-Object { $_ -ne $AndroidStep })
if ($wantAndroid) { $Steps = $Steps + $AndroidStep }

$lines = [System.Collections.Generic.List[string]]::new()
$started = Get-Date
$anyFail = $false
foreach ($name in $Steps) {
    if ($anyFail -and -not $KeepGoing) {
        $line = "SKIP ${name}: an earlier step failed (use -KeepGoing to run it anyway)"
    }
    elseif (-not $StepTable.Contains($name)) {
        $anyFail = $true
        $line = "FAIL ${name}: unknown step (known: $(@($StepTable.Keys) -join ', '))"
    }
    else {
        $t0 = Get-Date
        try { $r = & $StepTable[$name] }
        catch { $r = New-StepResult $false "exception: $($_.Exception.Message)" }
        $secs = [int]((Get-Date) - $t0).TotalSeconds
        if (-not $r.Ok) { $anyFail = $true }
        $line = "{0} {1}: {2} ({3} s)" -f ($(if ($r.Ok) { "PASS" } else { "FAIL" })), $name, $r.Detail, $secs
    }
    Write-Host $line
    $lines.Add($line)
}

$verdict = if ($anyFail) { "FAIL" } else { "PASS" }
$summary = @(
    "Painter IO verify - $($started.ToString('yyyy-MM-dd HH:mm:ss')) - agent $Agent - steps: $($Steps -join ', ')"
) + $lines + @("OVERALL $verdict")
$summary | Out-File -LiteralPath (Join-Path $root "docs/verify_last.txt") -Encoding utf8
Write-Host "OVERALL $verdict"
if ($anyFail) { exit 1 } else { exit 0 }
