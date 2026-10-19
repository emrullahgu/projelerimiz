param([string[]]$Parcels = @('2', '3', '4', '5'))
# CLD - applies the 9 LISPs to each parcel DWG (fresh copy of the architect's file), saves the result
# and plots every sheet to PDF. Only processes started here are ever waited on / stopped.
$sp = 'C:\Users\emrul\AppData\Local\Temp\claude\C--Users-emrul-OneDrive-Masa-st--Brosco\b334ee63-b347-42fb-909d-45b521dd643c\scratchpad'
$out = (Resolve-Path "$env:USERPROFILE\OneDrive\Masa*\Brosco\CLAUDE_LISP_BROSCO").Path
$acc = 'C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe'
$py = "$sp\venv\Scripts\python.exe"
foreach ($n in $Parcels) {
  $run = Join-Path $sp "final\P$n"
  if (Test-Path $run) { Remove-Item $run -Recurse -Force }
  New-Item -ItemType Directory -Force "$run\lsp", "$run\pdf" | Out-Null
  Copy-Item "$out\PARSEL_$n\CLD_P${n}_*.lsp" "$run\lsp"
  $plane = 'xy'
  if ((Get-Content "$out\PARSEL_$n\CLD_P${n}_01_*.lsp" | Select-String -SimpleMatch '(setq *cld-ext* (list 0.0 -1.0 0.0))')) { $plane = 'xz' }
  & $py "$sp\tools\final_scr.py" $out $run $n $plane
  "=== P$n plane=$plane $(Get-Date -Format HH:mm:ss)"
  $t0 = Get-Date
  $p = Start-Process -FilePath $acc -ArgumentList @('/i', "`"$sp\dwg\P$n.dwg`"", '/s', "`"$run\final.scr`"", '/l', 'en-US') -RedirectStandardOutput "$run\final.log" -NoNewWindow -PassThru
  if (-not $p.WaitForExit(90 * 60 * 1000)) { Stop-Process -Id $p.Id -Force; 'TIMEOUT' }
  "elapsed $([int]((Get-Date) - $t0).TotalSeconds) s"
  $log = (Get-Content "$run\final.log" -Raw) -replace "`0", ''
  $log -split "`n" | Where-Object { $_ -match 'CLD: Parsel|CLD UYARI|#CLD-(LOADED|SAVED|DONE)|Invalid|error' } | Select-Object -First 40
  "pdf: $((Get-ChildItem "$run\pdf" -Filter *.pdf).Count)  dwg: $([int]((Get-Item "$run\out.dwg" -ErrorAction SilentlyContinue).Length / 1MB)) MB"
}
'ALL DONE'
