# RenderLab runs (B1's "-renderlab <dir>": touching colors, thin strips, a rotated square, a fill) of a release player at
# 540 x 960 on several tiers, in parallel. Output: <OutRoot>/renderlab_<tier>/lab_*.png plus p.log.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$OutRoot,
    [string]$Tiers = "high,medium",
    [int]$W = 540,
    [int]$H = 960,
    [int]$TimeoutSeconds = 240
)
$procs = @()
foreach ($tier in $Tiers.Split(",")) {
    $dir = Join-Path $OutRoot "renderlab_$tier"
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    [void](New-Item -ItemType Directory $dir -Force)
    $log = Join-Path $dir "p.log"
    $a = "-renderlab `"$dir`" -quality $tier -screen-width $W -screen-height $H -screen-fullscreen 0 -logFile `"$log`""
    $p = Start-Process -FilePath $Exe -ArgumentList $a -PassThru
    $procs += [pscustomobject]@{ Tier = $tier; Proc = $p; Dir = $dir; Start = Get-Date }
}
foreach ($s in $procs) {
    if (-not $s.Proc.WaitForExit($TimeoutSeconds * 1000)) { $s.Proc.Kill(); "$($s.Tier): TIMEOUT"; continue }
    $n = @(Get-ChildItem $s.Dir -Filter *.png).Count
    "$($s.Tier): exit=$($s.Proc.ExitCode) pngs=$n"
}
