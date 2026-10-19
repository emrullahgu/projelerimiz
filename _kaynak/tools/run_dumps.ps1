param([string[]]$Parcels = @('5','2','3','4'))
$sp = 'C:\Users\emrul\AppData\Local\Temp\claude\C--Users-emrul-OneDrive-Masa-st--Brosco\b334ee63-b347-42fb-909d-45b521dd643c\scratchpad'
$acc = 'C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe'
$need = @{ '5' = 5; '2' = 6; '3' = 9; '4' = 12 }
foreach ($p in $Parcels) {
  $t0 = Get-Date
  while ($true) {
    $free = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    if ($free -ge $need[$p]) { break }
    if (((Get-Date) - $t0).TotalMinutes -gt 60) { "P$p : waited 60 min, starting anyway (free=$free GB)"; break }
    Start-Sleep -Seconds 15
  }
  "P$p start $(Get-Date -Format HH:mm:ss) free=$([math]::Round($free,1))GB"
  $log = Join-Path $sp "dump\P$p.log"
  $proc = Start-Process -FilePath $acc -ArgumentList @('/i', "`"$sp\dwg\P$p.dwg`"", '/s', "`"$sp\tools\dump_P$p.scr`"", '/l', 'en-US') -RedirectStandardOutput $log -NoNewWindow -PassThru
  if (-not $proc.WaitForExit(45 * 60 * 1000)) { Stop-Process -Id $proc.Id -Force; "P$p TIMEOUT" }
  $out = Join-Path $sp "dump\P$p.txt"
  "P$p end $(Get-Date -Format HH:mm:ss) exists=$(Test-Path $out) size=$(if (Test-Path $out) {(Get-Item $out).Length} else {0})"
}
