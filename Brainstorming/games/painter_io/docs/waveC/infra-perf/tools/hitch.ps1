# Hitch and minimize checks for the release player (wave C infra-perf acceptance).
# -Mode menu: plain player (menu attract), suspended for -SuspendMs at -SuspendAt s after launch, killed at -Total s.
# -Mode probe: probe run (-fps 60, Auto tier), suspended -SuspendAt s after "[Probe] bot round started"; waits for exit.
# -Mode minimize: plain player in the menu; CPU ms per s visible, then minimized (SW_MINIMIZE), like
#   docs/waveC/robust-refute/minimize/result.txt.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [ValidateSet("menu", "probe", "minimize")][string]$Mode = "menu",
    [double]$SuspendAt = 12,
    [int]$SuspendMs = 1500,
    [double]$Total = 30,
    [switch]$NoSuspend
)
$ErrorActionPreference = "Stop"
Add-Type -Namespace PioHitch -Name Native -MemberDefinition @'
[DllImport("ntdll.dll")] public static extern int NtSuspendProcess(System.IntPtr h);
[DllImport("ntdll.dll")] public static extern int NtResumeProcess(System.IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool IsIconic(System.IntPtr hWnd);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, System.UIntPtr extra);
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
'@
if (Test-Path -LiteralPath $OutDir) { Remove-Item -LiteralPath $OutDir -Recurse -Force }
[void](New-Item -ItemType Directory -Path $OutDir -Force)
$log = Join-Path $OutDir "p.log"
$result = Join-Path $OutDir "result.txt"
$argv = @("-screen-width", "540", "-screen-height", "960", "-screen-fullscreen", "0", "-logFile", "`"$log`"")
if ($Mode -eq "probe") { $argv = @("-probe", "-shotdir", "`"$OutDir`"", "-fps", "60", "-mute", "-biome", "liquid") + $argv }
$p = Start-Process -FilePath $Exe -ArgumentList ($argv -join ' ') -PassThru
$null = $p.Handle
$t0 = Get-Date
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("mode=$Mode exe=$Exe suspendAt=$SuspendAt suspendMs=$SuspendMs noSuspend=$NoSuspend")

function Suspend-Briefly {
    if ($NoSuspend) { $lines.Add("no suspension (control)"); return }
    $at = ((Get-Date) - $t0).TotalSeconds
    [void][PioHitch.Native]::NtSuspendProcess($p.Handle)
    Start-Sleep -Milliseconds $SuspendMs
    [void][PioHitch.Native]::NtResumeProcess($p.Handle)
    $lines.Add(("suspended {0} ms at t={1:0.0} s after launch" -f $SuspendMs, $at))
}

if ($Mode -eq "menu") {
    Start-Sleep -Seconds 6
    $p.Refresh(); $hw = $p.MainWindowHandle
    [PioHitch.Native]::keybd_event(0x12, 0, 0, [System.UIntPtr]::Zero); [PioHitch.Native]::keybd_event(0x12, 0, 2, [System.UIntPtr]::Zero)
    [void][PioHitch.Native]::SetForegroundWindow($hw)
    $lines.Add("foreground=$([PioHitch.Native]::GetForegroundWindow() -eq $hw)")
    Start-Sleep -Milliseconds ([int](($SuspendAt - 6) * 1000))
    Suspend-Briefly
    $left = $Total - ((Get-Date) - $t0).TotalSeconds
    if ($left -gt 0) { Start-Sleep -Milliseconds ([int]($left * 1000)) }
    try { $p.Kill($true) } catch { }
}
elseif ($Mode -eq "probe") {
    $deadline = (Get-Date).AddSeconds(240)
    $started = $false
    while (-not $p.HasExited -and (Get-Date) -lt $deadline) {
        if ((Test-Path -LiteralPath $log) -and (Select-String -LiteralPath $log -Pattern '^\[Probe\] bot round started' -Quiet)) { $started = $true; break }
        Start-Sleep -Milliseconds 200
    }
    $lines.Add("bot round seen=$started at t=$([math]::Round(((Get-Date) - $t0).TotalSeconds, 1)) s")
    if ($started) {
        Start-Sleep -Milliseconds ([int]($SuspendAt * 1000))
        Suspend-Briefly
    }
    if (-not $p.WaitForExit(300000)) { try { $p.Kill($true) } catch { }; $lines.Add("timeout, killed") }
    $lines.Add("exit=$($p.ExitCode)")
}
else {
    # minimize
    Start-Sleep -Seconds 12
    $p.Refresh()
    $hwnd = $p.MainWindowHandle
    $lines.Add("hwnd=$hwnd")
    [PioHitch.Native]::keybd_event(0x12, 0, 0, [System.UIntPtr]::Zero); [PioHitch.Native]::keybd_event(0x12, 0, 2, [System.UIntPtr]::Zero)
    [void][PioHitch.Native]::SetForegroundWindow($hwnd)
    $lines.Add("foreground=$([PioHitch.Native]::GetForegroundWindow() -eq $hwnd)")
    Start-Sleep -Seconds 2
    $p.Refresh(); $c0 = $p.TotalProcessorTime.TotalMilliseconds; $w0 = Get-Date
    Start-Sleep -Seconds 10
    $p.Refresh(); $c1 = $p.TotalProcessorTime.TotalMilliseconds; $w1 = Get-Date
    $lines.Add(("visible ms/s: {0:0}" -f (($c1 - $c0) / ($w1 - $w0).TotalSeconds)))
    [void][PioHitch.Native]::ShowWindow($hwnd, 6)   # SW_MINIMIZE
    Start-Sleep -Seconds 3
    $lines.Add("iconic=$([PioHitch.Native]::IsIconic($hwnd))")
    $p.Refresh(); $c2 = $p.TotalProcessorTime.TotalMilliseconds; $w2 = Get-Date
    Start-Sleep -Seconds 10
    $p.Refresh(); $c3 = $p.TotalProcessorTime.TotalMilliseconds; $w3 = Get-Date
    $ms = ($c3 - $c2) / ($w3 - $w2).TotalSeconds
    $lines.Add(("minimized ms/s: {0:0} ({1:0.0} % of one core)" -f $ms, ($ms / 10.0)))
    try { $p.Kill($true) } catch { }
}
Start-Sleep -Milliseconds 500
$text = if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Raw } else { "" }
$wd = @(([regex]::Matches("$text", '(?m)^\[PainterIO\] quality watchdog.*$')) | ForEach-Object { $_.Value.Trim() })
$lines.Add("watchdog lines: $($wd.Count) $($wd -join ' | ')")
foreach ($pat in '^\[ProbeResult\].*$', '^\[ProbeHash\].*$', '^\[ProbePerf\].*$', '^\[PainterIO\] render scale.*$') {
    $m = [regex]::Matches("$text", "(?m)$pat")
    if ($m.Count -gt 0) { $lines.Add($m[$m.Count - 1].Value.Trim()) }
}
$lines | Out-File -LiteralPath $result -Encoding utf8
$lines



