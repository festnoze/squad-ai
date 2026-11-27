# Runs one DevShot of a Painter IO player and waits for it to quit.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Biome = "electric",
    [string]$Quality = "",
    [int]$W = 540,
    [int]$H = 960,
    [int]$TimeoutSeconds = 300
)
New-Item -ItemType Directory -Force $OutDir | Out-Null
$args2 = @("-devshot", $OutDir, "-biome", $Biome, "-screen-width", "$W", "-screen-height", "$H", "-screen-fullscreen", "0", "-logFile", (Join-Path $OutDir "p.log"))
if ($Quality) { $args2 += @("-quality", $Quality) }
$p = Start-Process -FilePath $Exe -ArgumentList $args2 -PassThru
if (-not $p.WaitForExit($TimeoutSeconds * 1000)) { $p.Kill(); "TIMEOUT $OutDir" } else { "exit=$($p.ExitCode) $OutDir" }
Select-String -Path (Join-Path $OutDir "p.log") -Pattern '\[DevShot\] (scenario|done|saved)|Exception' | ForEach-Object { $_.Line }
