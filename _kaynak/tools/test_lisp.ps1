param([string]$Parcel = '5', [string]$Files = '*')
$sp = 'C:\Users\emrul\AppData\Local\Temp\claude\C--Users-emrul-OneDrive-Masa-st--Brosco\b334ee63-b347-42fb-909d-45b521dd643c\scratchpad'
$out = (Resolve-Path "$env:USERPROFILE\OneDrive\Masa*\Brosco\CLAUDE_LISP_BROSCO").Path
$acc = 'C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe'
$td = Join-Path $sp "test\P$Parcel"
New-Item -ItemType Directory -Force $td | Out-Null
Remove-Item "$td\*" -Force -ErrorAction SilentlyContinue
Copy-Item "$out\PARSEL_$Parcel\CLD_P${Parcel}_$Files.lsp" $td
$spf = $sp -replace '\\', '/'
$tdf = $td -replace '\\', '/'
$lines = @("(setvar `"TRUSTEDPATHS`" `"$tdf;$spf/tools`")")
foreach ($f in (Get-ChildItem $td -Filter '*.lsp' | Sort-Object Name)) {
  $lines += "(load `"$tdf/$($f.Name)`")"
}
$lines += "(command `"_.-LAYER`" `"_LOCK`" `"CLD-P$Parcel-ICT-ALTLIK`" `"`")"
$lines += "(c:CLD_P$($Parcel)_ICTESISAT)"
$lines += "(load `"$spf/tools/cldx_dump.lsp`")"
$lines += "(cldx:dump `"$tdf/after.txt`")"
$scr = Join-Path $td 'test.scr'
[System.IO.File]::WriteAllLines($scr, $lines, [System.Text.Encoding]::GetEncoding(1254))
$t0 = Get-Date
$p = Start-Process -FilePath $acc -ArgumentList @('/i', "`"$sp\dwg\P$Parcel.dwg`"", '/s', "`"$scr`"", '/l', 'en-US') -RedirectStandardOutput "$td\test.log" -NoNewWindow -PassThru
if (-not $p.WaitForExit(40 * 60 * 1000)) { Stop-Process -Id $p.Id -Force; 'TIMEOUT' }
"elapsed $([int]((Get-Date) - $t0).TotalSeconds) s"
$log = (Get-Content "$td\test.log" -Raw) -replace "`0", ''
$log -split "`n" | Where-Object { $_ -match 'CLD|error|HATA|bad|nil' } | Select-Object -First 60
