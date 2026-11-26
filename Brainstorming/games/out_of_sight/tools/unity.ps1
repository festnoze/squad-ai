# Runs the Unity CLI with an exclusive lock on this project: the PowerShell twin of tools/unity.sh, for when Git Bash
# hangs. Unity refuses to open a project another editor holds, so every agent goes through one lock directory.
#
# Usage (one string, arguments split on spaces, so no argument may contain a space):
#   pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "run . --timeout 1800 -- -executeMethod OutOfSight.Editor.Builder.SetupAndCompile -logFile Build/x.log"
#   pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "test . --mode PlayMode --filter Step65a_|Step26_ --report-format junit --output TestResults/x.xml --timeout 1800"
#
# How the lock works (LOCKFIX, 2026-11-22):
# - The lock is the directory .unity.lock with an "owner" file inside. It is taken by building the directory with its
#   owner file under Logs/ and renaming it to .unity.lock in one step (a rename fails when the target exists), so a lock
#   is never seen without its owner.
# - The owner file keeps the historical first line "<pid> <agent> <args>" (read by tools/unity.sh and by older copies
#   of this script), followed by key=value lines: format, token, pid, start (process start time, UTC ticks), host,
#   heartbeat (UTC ticks) and children (Unity processes launched by the holder, as pid:start ticks). It is always
#   rewritten through a temporary file and an atomic rename.
# - The holder keeps a "pin" file open inside the lock (no delete sharing) for as long as it runs: Windows then
#   refuses to rename or delete the lock directory, so no waiter (new, old or tools/unity.sh) can remove a live lock.
# - A background thread of the holder refreshes the heartbeat and the children every few seconds, and restores the
#   owner file if an older waiter deleted it (the pin kept the directory).
# - A waiter judges a lock ONLY from its owner file: live while the owner process runs with the same start time, or
#   one of its Unity children does, or its heartbeat is fresh. The directory creation time is never used: Windows
#   keeps the old creation time on a directory re-created under the same name (file system tunneling), which made a
#   fresh lock look old and let a waiter steal it.
# - An old format owner (first line only, from tools/unity.sh or an older copy of this script) is live while its pid
#   runs, or while the directory was written to in the last 150 s (tools/unity.sh touches it as its heartbeat).
# - A stale verdict must hold on two polls in a row on the same owner text, and the takeover renames the lock away
#   only if the owner text is still the one judged stale (and gives it back if it changed hands meanwhile).
# - On release, the lock is removed only if its owner token is still ours.
param(
    [Parameter(Mandatory = $true)][string]$UnityArgs,
    [string]$Agent = "shell"
)

$project = Split-Path -Parent $PSScriptRoot
$lock = Join-Path $project ".unity.lock"
$owner = Join-Path $lock "owner"
$unityExe = Join-Path $env:LOCALAPPDATA "Unity\bin\unity.exe"
$staging = Join-Path $project "Logs"
$lockLog = Join-Path $staging "unity-lock.log"
$pollSeconds = 10
$beatSeconds = 20
$firstBeatSeconds = 3
$beatStaleSeconds = 90
$ownerlessGraceSeconds = 60
$oldOwnerQuietSeconds = 150

# Shared by the main thread and the heartbeat thread.
$lockLib = @'
function Read-LockOwner([string]$path) {
    # The owner text, "" when there is no owner file, $null when it cannot be read right now.
    try {
        $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
        $fs = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, $share)
        try {
            $reader = [System.IO.StreamReader]::new($fs)
            return $reader.ReadToEnd()
        }
        finally { $fs.Dispose() }
    }
    catch [System.IO.FileNotFoundException] { return "" }
    catch [System.IO.DirectoryNotFoundException] { return "" }
    catch { return $null }
}

function Write-LockOwner([string]$path, [string]$text) {
    # Atomic replace: readers see the old text or the new one, never a partial file.
    $tmp = "$path.$PID.tmp"
    [System.IO.File]::WriteAllText($tmp, $text)
    try { [System.IO.File]::Move($tmp, $path, $true) }
    catch [System.Management.Automation.MethodException] {
        if (Test-Path -LiteralPath $path) { [System.IO.File]::Replace($tmp, $path, $null) }
        else { [System.IO.File]::Move($tmp, $path) }
    }
}

function Get-UnityDescendants([int]$root) {
    # Unity processes started (directly or not) by $root, as "pid:start ticks" strings.
    $all = @(Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, Name, CreationDate -ErrorAction Stop)
    $byParent = @{}
    $start = @{}
    foreach ($p in $all) {
        $start[[int]$p.ProcessId] = if ($p.CreationDate) { $p.CreationDate.ToUniversalTime().Ticks } else { [long]0 }
        $key = [int]$p.ParentProcessId
        if (-not $byParent.ContainsKey($key)) { $byParent[$key] = [System.Collections.Generic.List[object]]::new() }
        $byParent[$key].Add($p)
    }
    $found = [System.Collections.Generic.List[string]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $seen = @{}
    $queue.Enqueue($root)
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        if ($seen.ContainsKey($parent)) { continue }
        $seen[$parent] = $true
        if (-not $byParent.ContainsKey($parent)) { continue }
        foreach ($child in $byParent[$parent]) {
            $cid = [int]$child.ProcessId
            # A child older than its parent belongs to an earlier owner of a recycled pid.
            if ($start[$parent] -and $start[$cid] -and $start[$cid] -lt $start[$parent]) { continue }
            if ($child.Name -match 'unity') { $found.Add("${cid}:$($start[$cid])") }
            $queue.Enqueue($cid)
        }
    }
    return $found
}
'@
. ([scriptblock]::Create($lockLib))

function Write-LockLog([string]$message) {
    try { Add-Content -LiteralPath $lockLog -Value ("{0:yyyy-MM-dd HH:mm:ss} [pid {1} {2}] {3}" -f (Get-Date), $PID, $Agent, $message) }
    catch { }
}

function Test-SameProcess([int]$id, [long]$ticks) {
    # True while process $id runs and started at $ticks (2 s tolerance); an unreadable start time counts as a match.
    if ($id -le 0) { return $false }
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    if ($ticks -le 0) { return $true }
    try { $now = $p.StartTime.ToUniversalTime().Ticks } catch { return $true }
    return [math]::Abs($now - $ticks) -lt 20000000
}

function Get-LockVerdict([string]$text, [datetime]$dirWriteUtc) {
    # "live", "dead" or "ownerless" (no owner yet, or an owner that cannot be parsed).
    $lines = $text -split "`r?`n"
    $kv = @{}
    foreach ($line in $lines) { if ($line -match '^([a-z]+)=(.*)$') { $kv[$Matches[1]] = $Matches[2].Trim() } }
    $firstPid = 0
    [void][int]::TryParse((($lines[0] -split ' ')[0]), [ref]$firstPid)
    $nowTicks = [datetime]::UtcNow.Ticks

    if ($kv['format'] -eq '2') {
        $ownerPid = 0; [void][int]::TryParse($kv['pid'], [ref]$ownerPid)
        $start = [long]0; [void][long]::TryParse($kv['start'], [ref]$start)
        $beat = [long]0; [void][long]::TryParse($kv['heartbeat'], [ref]$beat)
        $fresh = ($nowTicks - $beat) -lt ([long]$beatStaleSeconds * 10000000)
        if ($kv['host'] -and $kv['host'] -ne $env:COMPUTERNAME) {
            # Another machine: its processes are out of sight, only the heartbeat speaks for it.
            if ($fresh) { return "live" } else { return "dead" }
        }
        if (Test-SameProcess $ownerPid $start) { return "live" }
        foreach ($entry in ("$($kv['children'])" -split ',')) {
            $parts = $entry -split ':'
            if ($parts.Count -ne 2) { continue }
            $cid = 0; $cstart = [long]0
            if ([int]::TryParse($parts[0], [ref]$cid) -and [long]::TryParse($parts[1], [ref]$cstart)) {
                if (Test-SameProcess $cid $cstart) { return "live" }
            }
        }
        if ($fresh) { return "live" }
        return "dead"
    }
    if ($firstPid -gt 0) {
        # Old format: a pid alone, so pid reuse is accepted as "live" (the safe side).
        if (Get-Process -Id $firstPid -ErrorAction SilentlyContinue) { return "live" }
        if (([datetime]::UtcNow - $dirWriteUtc).TotalSeconds -lt $oldOwnerQuietSeconds) { return "live" }
        return "dead"
    }
    return "ownerless"
}

function Get-OwnerHeader {
    return "$PID $Agent $UnityArgs`nformat=2`ntoken=$token`npid=$PID`nstart=$myStart`nhost=$env:COMPUTERNAME`n"
}

function Enter-Lock {
    # Builds the lock with its owner file aside, then renames it into place: the rename fails if the lock exists.
    if (Test-Path -LiteralPath $lock) { return $false }
    $stage = Join-Path $staging "unity-lock-new-$token"
    try {
        [void][System.IO.Directory]::CreateDirectory($stage)
        $text = (Get-OwnerHeader) + "heartbeat=$([datetime]::UtcNow.Ticks)`nchildren=`n"
        [System.IO.File]::WriteAllText((Join-Path $stage "owner"), $text)
        [System.IO.Directory]::Move($stage, $lock)
        return $true
    }
    catch {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        return $false
    }
}

function Remove-StaleLock([string]$expected) {
    # Takes over a lock judged stale with owner text $expected, only if it still is that lock.
    $again = Read-LockOwner $owner
    if ($null -eq $again -or $again -ne $expected) { return $false }
    $tomb = Join-Path $staging ("unity-lock-stale-" + [guid]::NewGuid().ToString('N'))
    try { [System.IO.Directory]::Move($lock, $tomb) } catch { return $false }
    $moved = Read-LockOwner (Join-Path $tomb "owner")
    if ($moved -ne $expected) {
        # It changed hands between the check and the rename: give it back.
        try {
            [System.IO.Directory]::Move($tomb, $lock)
            Write-LockLog "a lock changed hands during a takeover; given back"
            return $false
        }
        catch { Write-LockLog "a lock changed hands during a takeover and could not be given back: '$(($moved -split "`n")[0])'" }
    }
    else {
        Write-LockLog "took over a stale lock, holder was: '$(($expected -split "`n")[0])'"
    }
    Remove-Item -LiteralPath $tomb -Recurse -Force -ErrorAction SilentlyContinue
    return $true
}

$token = [guid]::NewGuid().ToString('N')
$myStart = [long]0
try { $myStart = (Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks } catch { }
if (-not (Test-Path -LiteralPath $staging)) { [void][System.IO.Directory]::CreateDirectory($staging) }

$deadKey = $null
$ownerlessKey = $null
$ownerlessSince = [datetime]::UtcNow
while ($true) {
    if (Enter-Lock) { break }
    $text = Read-LockOwner $owner
    $dir = Get-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue
    if (-not $dir) {
        # Released meanwhile: try again at once.
        $deadKey = $null
        Start-Sleep -Milliseconds 250
        continue
    }
    $verdict = "live"
    if ($null -ne $text) {
        $verdict = Get-LockVerdict $text $dir.LastWriteTimeUtc
        if ($verdict -eq "ownerless") {
            # Judged on this waiter's own clock, never on the directory's dates.
            if ($ownerlessKey -ne $text) { $ownerlessKey = $text; $ownerlessSince = [datetime]::UtcNow }
            $verdict = if (([datetime]::UtcNow - $ownerlessSince).TotalSeconds -ge $ownerlessGraceSeconds) { "dead" } else { "live" }
        }
        else { $ownerlessKey = $null }
    }
    if ($verdict -eq "dead") {
        if ($deadKey -eq $text) {
            $deadKey = $null
            if (Remove-StaleLock $text) { continue }
        }
        else { $deadKey = $text }
    }
    else { $deadKey = $null }
    Start-Sleep -Seconds $pollSeconds
}

$code = 1
$pin = $null
$beat = $null
$beatRun = $null
$beatSpace = $null
try {
    try {
        $pin = [System.IO.FileStream]::new((Join-Path $lock "pin"), [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    }
    catch { Write-LockLog "could not pin the lock: $($_.Exception.Message)" }
    # Heartbeat thread: refreshes the heartbeat and the Unity children while the lock is ours.
    $state = [hashtable]::Synchronized(@{
        Stop = [System.Threading.ManualResetEvent]::new($false)
        Owner = $owner; Token = $token; Header = (Get-OwnerHeader); Root = $PID; Children = ""
        Pinned = ($null -ne $pin); FirstMs = $firstBeatSeconds * 1000; BeatMs = $beatSeconds * 1000
    })
    $beatSpace = [runspacefactory]::CreateRunspace()
    $beatSpace.Open()
    $beatSpace.SessionStateProxy.SetVariable('state', $state)
    $beat = [powershell]::Create()
    $beat.Runspace = $beatSpace
    [void]$beat.AddScript($lockLib + @'

$wait = $state.FirstMs
while (-not $state.Stop.WaitOne($wait)) {
    $wait = $state.BeatMs
    try {
        # The slow process scan first, so the check below and the write stay back to back.
        try { $state.Children = (Get-UnityDescendants $state.Root) -join ',' } catch { }
        $current = Read-LockOwner $state.Owner
        if ($null -eq $current) { continue }
        # No owner file: restored only under the pin, which proves the directory is still ours.
        if ($current -eq "" -and -not $state.Pinned) { break }
        # Another owner wrote over the lock: never fight it.
        if ($current -ne "" -and $current -notmatch "(?m)^token=$($state.Token)\s*$") { break }
        Write-LockOwner $state.Owner ($state.Header + "heartbeat=$([datetime]::UtcNow.Ticks)`nchildren=$($state.Children)`n")
    }
    catch { }
}
'@)
    $beatRun = $beat.BeginInvoke()

    $env:UNITY_NO_BANNER = 1
    $env:UNITY_NON_INTERACTIVE = 1
    Set-Location $project
    $argv = $UnityArgs -split '\s+' | Where-Object { $_ -ne '' }
    & $unityExe @argv
    $code = $LASTEXITCODE
}
finally {
    if ($beat) {
        $state.Stop.Set()
        if ($beatRun) { [void]$beatRun.AsyncWaitHandle.WaitOne(5000) }
        $beat.Dispose()
    }
    if ($beatSpace) { $beatSpace.Dispose() }
    $current = $null
    for ($i = 0; $i -lt 10 -and $null -eq $current; $i++) {
        $current = Read-LockOwner $owner
        if ($null -eq $current) { Start-Sleep -Milliseconds 200 }
    }
    # The pin blocks the rename below: drop it first.
    if ($pin) { $pin.Dispose() }
    if ($current -match "(?m)^token=$token\s*$") {
        $released = $false
        for ($i = 0; $i -lt 10 -and -not $released; $i++) {
            try {
                $tomb = Join-Path $staging "unity-lock-done-$token"
                [System.IO.Directory]::Move($lock, $tomb)
                Remove-Item -LiteralPath $tomb -Recurse -Force -ErrorAction SilentlyContinue
                $released = $true
            }
            catch { Start-Sleep -Milliseconds 200 }
        }
        if (-not $released) { Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue }
    }
    elseif ($null -ne $current) {
        Write-LockLog "the lock was no longer ours at release; left it alone"
    }
}
exit $code
