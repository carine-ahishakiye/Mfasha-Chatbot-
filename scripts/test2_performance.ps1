param([string]$Mode = "warm")

$base   = "https://mfasha-chatbot.vercel.app/mfasha"
$budget = 5000
$root   = Split-Path -Parent $PSScriptRoot
$out    = Join-Path $root "results\system_testing"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$file   = Join-Path $out "test2_performance.csv"

function Ask($q) {
  $p = @{ Uri = "$base/api/ask/text"; Method = "POST"; UseBasicParsing = $true; TimeoutSec = 120
          Body = [Text.Encoding]::UTF8.GetBytes((@{ question = $q } | ConvertTo-Json -Compress)); ContentType = "application/json; charset=utf-8" }
  $sw = [Diagnostics.Stopwatch]::StartNew(); $code = 0; $j = $null
  try {
    $r = Invoke-WebRequest @p; $code = [int]$r.StatusCode
    try { $j = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json } catch { $j = $null }
  } catch { if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } else { $code = -1 } }
  [pscustomobject]@{ Code = $code; J = $j; Ms = [int]$sw.Elapsed.TotalMilliseconds }
}

function AppUp {
  try {
    $r = Invoke-WebRequest -Uri "$base/api/health" -UseBasicParsing -TimeoutSec 10
    $j = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
    return ($j.status -eq "ok")
  } catch { return $false }
}

function Pct($a, $p) {
  $s = @($a | Sort-Object); if ($s.Count -eq 0) { return 0 }
  $i = [math]::Ceiling($p / 100 * $s.Count) - 1; if ($i -lt 0) { $i = 0 }; return $s[$i]
}

function Save($new) {
  $keep = @()
  if (Test-Path $file) { $keep = @(Import-Csv $file -Encoding UTF8 | Where-Object { $_.Mode -ne $Mode }) }
  (@($keep) + @($new)) | Export-Csv -Path $file -NoTypeInformation -Encoding UTF8
}

function Row($n, $q, $code, $status, $server, $ms, $aid, $note) {
  [pscustomobject]@{ Mode = $Mode; N = $n; Question = $q; HTTP = $code; Status = $status; ServerMs = $server
    RoundTripMs = $ms; AnswerId = $aid; Note = $note; Time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
}

if ($Mode -eq "warm") {
  $qs = @("Ni gute nahinga ibigori?", "Ibirayi bitera mu butaka bumeze bute?", "Ni gute nakora ubuhinzi bw'ibihumyo?", "Ibibabi by'ibishyimbo byahinduye ibara",
          "Inkoko nzorora nte?", "Ni nde watwaye igikombe cy'isi cya 2022?", "Nakwirinda nte ibyonnyi mu bigori?", "Ni ryari nakingiza inka?",
          "Iteganyagihe ryamfasha iki mu buhinzi?", "Nabona nte nkunganire ku ifumbire?")
  $rows = @()
  Write-Host "WARM test: 50 sequential questions, 0.5 s pause between them`n" -ForegroundColor Cyan
  for ($i = 0; $i -lt 50; $i++) {
    $q = $qs[$i % 10]; $r = Ask $q
    $rows += Row ($i + 1) $q $r.Code $r.J.status $r.J.latency_ms $r.Ms $r.J.answer_id ""
    if (($i + 1) % 10 -eq 0) { Write-Host ("  {0} of 50 done" -f ($i + 1)) }
    Start-Sleep -Milliseconds 500
  }
  Save $rows
  $ok  = @($rows | Where-Object { $_.HTTP -eq 200 })
  $rt  = @($ok | ForEach-Object { [int]$_.RoundTripMs })
  $srv = @($ok | Where-Object { $_.ServerMs -ne $null -and $_.ServerMs -ne "" } | ForEach-Object { [double]$_.ServerMs })
  $errPct = [math]::Round(100 * ($rows.Count - $ok.Count) / $rows.Count, 1)
  $over = @($rt | Where-Object { $_ -gt $budget }).Count
  $p95 = Pct $rt 95
  Write-Host "`n===== WARM SUMMARY =====" -ForegroundColor Cyan
  Write-Host ("Requests: {0}   Errors: {1}%   Over {2} ms: {3}" -f $rows.Count, $errPct, $budget, $over)
  Write-Host ("Round trip ms:  p50 {0}   p95 {1}   max {2}   mean {3}" -f (Pct $rt 50), $p95, (Pct $rt 100), [int]($rt | Measure-Object -Average).Average)
  Write-Host ("Server ms:      p50 {0}   p95 {1}   (the rest of the round trip is network and proxy)" -f (Pct $srv 50), (Pct $srv 95))
  Write-Host ("First request: {0} ms" -f $rows[0].RoundTripMs)
  $verdict = "FAIL"; if ($p95 -le $budget -and $errPct -lt 1) { $verdict = "PASS" }
  Write-Host ("VERDICT: {0}  (target: p95 <= {1} ms and errors < 1%)" -f $verdict, $budget) -ForegroundColor Cyan
  Write-Host "Saved: $file"
}
elseif ($Mode -eq "cold") {
  if (-not (AppUp)) { Write-Host "The app is not up right now. Wait until it is, then run this again." -ForegroundColor Red; return }
  Write-Host "COLD START test" -ForegroundColor Cyan
  Write-Host "Leave this window open. Now go to your Space > Settings > Restart this Space, and click it." -ForegroundColor Yellow
  Write-Host ("Watching the app since {0}. It must fail 1 check to count as down (waits up to 5 minutes)..." -f (Get-Date).ToString("HH:mm:ss"))
  $start = Get-Date; $down = $null; $fails = 0; $firstFail = $null
  while (((Get-Date) - $start).TotalSeconds -lt 300) {
    if (AppUp) { $fails = 0; $firstFail = $null }
    else { if ($fails -eq 0) { $firstFail = Get-Date }; $fails++ }
    if ($fails -ge 1) { $down = $firstFail; break }
    Start-Sleep -Seconds 1
  }
  if (-not $down) { Write-Host "The app never went down. Did you click Restart?" -ForegroundColor Red; return }
  Write-Host ("App went down at {0}. Waiting for it to answer a real question (up to 20 minutes)..." -f $down.ToString("HH:mm:ss"))
  $up = $null; $first = $null
  while (((Get-Date) - $down).TotalSeconds -lt 1200) {
    Start-Sleep -Seconds 3
    if (AppUp) {
      $r = Ask "Ni gute nahinga ibigori?"
      if ($r.Code -eq 200 -and $r.J.status) { $up = Get-Date; $first = $r; break }
    }
  }
  if (-not $up) { Write-Host "Still no real answer after 20 minutes. Check the Space logs." -ForegroundColor Red; return }
  $cold = [int](($up - $down).TotalSeconds)
  $aid = $first.J.answer_id
  Save @((Row 1 "(seconds from down to first real answer)" 200 "ready" "" ($cold * 1000) $aid "cold start"),
         (Row 2 "Ni gute nahinga ibigori?" $first.Code $first.J.status $first.J.latency_ms $first.Ms $aid "first question after start"))
  Write-Host "`n===== COLD SUMMARY =====" -ForegroundColor Cyan
  Write-Host ("Down at {0}, first real answer at {1}" -f $down.ToString("HH:mm:ss"), $up.ToString("HH:mm:ss"))
  Write-Host ("Cold start (down to first real answer): {0} seconds" -f $cold)
  Write-Host ("First question after start: HTTP {0}, status {1}, {2} ms, answer_id {3}" -f $first.Code, $first.J.status, $first.Ms, $aid)
  if ([int]$aid -le 5) { Write-Host "answer_id is small, so the database was wiped: this was a real restart." -ForegroundColor Green }
  else { Write-Host "answer_id is large, so the database was NOT wiped: this may not have been a full restart. Do not use this number." -ForegroundColor Red }
  Write-Host "Saved: $file"
}
else { Write-Host "Use -Mode warm or -Mode cold" -ForegroundColor Red }
