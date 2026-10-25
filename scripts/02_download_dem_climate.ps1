# Download Copernicus GLO-90 DEM tiles for mainland Spain + Balearics, and WorldClim 2.1 bioclim (2.5 arc-min).
# Copernicus DEM: open data on AWS (s3://copernicus-dem-90m), 1x1 degree COG tiles. Ocean tiles don't exist (404) and are skipped.
$root = Split-Path $PSScriptRoot -Parent
$dem = Join-Path $root "00_raw\dem\glo90"
$clim = Join-Path $root "00_raw\climate"
New-Item -ItemType Directory -Force $dem | Out-Null

$ok = 0
foreach ($lat in 35..43) {
    foreach ($lon in -10..4) {
        $ns = "N{0:D2}" -f $lat
        $ew = if ($lon -lt 0) { "W{0:D3}" -f (-$lon) } else { "E{0:D3}" -f $lon }
        $name = "Copernicus_DSM_COG_30_${ns}_00_${ew}_00_DEM"
        $out = Join-Path $dem "$name.tif"
        if (Test-Path $out) { $ok++; continue }
        curl.exe -sL --fail -o $out "https://copernicus-dem-90m.s3.amazonaws.com/$name/$name.tif" 2>$null
        if ($LASTEXITCODE -eq 0) { $ok++ } elseif (Test-Path $out) { Remove-Item $out }
    }
}
"DEM tiles: $ok"

$wc = Join-Path $clim "wc2.1_2.5m_bio.zip"
if (-not (Test-Path $wc)) { curl.exe -sL --fail -o $wc "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_bio.zip" }
"WorldClim: " + [math]::Round((Get-Item $wc).Length / 1MB, 1) + " MB"
