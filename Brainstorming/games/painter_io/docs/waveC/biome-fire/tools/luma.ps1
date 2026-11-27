# Counts pixels with luma >= threshold in a square window around given centres, and finds the brightest blobs.
param([string]$Png, [string]$Centres = "", [int]$Radius = 20, [int]$Threshold = 235, [switch]$Blobs)
Add-Type -AssemblyName System.Drawing
$bmp = [System.Drawing.Bitmap]::new($Png)
$w = $bmp.Width; $h = $bmp.Height
$rect = [System.Drawing.Rectangle]::new(0, 0, $w, $h)
$data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$stride = $data.Stride
$bytes = New-Object byte[] ($stride * $h)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
$bmp.UnlockBits($data); $bmp.Dispose()
function Luma([int]$x, [int]$y) {
    $i = $y * $stride + $x * 3
    return 0.2126 * $bytes[$i + 2] + 0.7152 * $bytes[$i + 1] + 0.0722 * $bytes[$i]
}
if ($Centres -ne "") {
    foreach ($c in $Centres.Split(';')) {
        $xy = $c.Split(','); $cx = [int]$xy[0]; $cy = [int]$xy[1]
        $n = 0; $max = 0
        for ($y = [Math]::Max(0, $cy - $Radius); $y -le [Math]::Min($h - 1, $cy + $Radius); $y++) {
            for ($x = [Math]::Max(0, $cx - $Radius); $x -le [Math]::Min($w - 1, $cx + $Radius); $x++) {
                $l = Luma $x $y
                if ($l -ge $Threshold) { $n++ }
                if ($l -gt $max) { $max = $l }
            }
        }
        "centre $cx,$cy r=$Radius : count(luma>=$Threshold)=$n max=$([int]$max)"
    }
}
if ($Blobs) {
    # Grid of 16 px tiles: count of bright pixels per tile, top 12.
    $tiles = @{}
    for ($y = 0; $y -lt $h; $y++) { for ($x = 0; $x -lt $w; $x++) { if ((Luma $x $y) -ge $Threshold) { $k = "$([int]($x/16)),$([int]($y/16))"; $tiles[$k] = 1 + $tiles[$k] } } }
    $tiles.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 15 | ForEach-Object { $t = $_.Key.Split(','); "tile x=$([int]$t[0]*16)..$([int]$t[0]*16+15) y=$([int]$t[1]*16)..$([int]$t[1]*16+15): $($_.Value)" }
}
