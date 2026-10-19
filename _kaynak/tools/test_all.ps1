param([string[]]$Parcels = @('2', '3', '4', '5'))
$t = 'C:\Users\emrul\AppData\Local\Temp\claude\C--Users-emrul-OneDrive-Masa-st--Brosco\b334ee63-b347-42fb-909d-45b521dd643c\scratchpad\tools\test_lisp.ps1'
foreach ($p in $Parcels) {
  while (((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB) -lt 6) { Start-Sleep -Seconds 15 }
  "=== P$p $(Get-Date -Format HH:mm:ss)"
  & $t -Parcel $p | Where-Object { $_ -match 'cizildi|error|HATA|bad|elapsed|TIMEOUT' }
}
"ALL DONE"
