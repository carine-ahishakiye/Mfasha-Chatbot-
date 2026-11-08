$base = "https://mfasha-chatbot.vercel.app/mfasha"
$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root "results\system_testing"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$file = Join-Path $out "test1_functional.csv"
$script:aid = $null

function Call($method, $path, $body, $raw) {
  $p = @{ Uri = "$base$path"; Method = $method; UseBasicParsing = $true; TimeoutSec = 120 }
  if ($raw) {
    $p.Body = [Text.Encoding]::UTF8.GetBytes($raw); $p.ContentType = "application/json"
  } elseif ($body) {
    $p.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress)); $p.ContentType = "application/json; charset=utf-8"
  }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $code = 0; $j = $null
  try {
    $r = Invoke-WebRequest @p
    $code = [int]$r.StatusCode
    try { $j = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json } catch { $j = $null }
  } catch {
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } else { $code = -1 }
  }
  [pscustomobject]@{ Code = $code; J = $j; Ms = [int]$sw.Elapsed.TotalMilliseconds }
}

function T($id, $name, $m, $p, $b, $raw, $code, $st, $obs) {
  @{ Id = $id; Name = $name; M = $m; P = $p; B = $b; Raw = $raw; Code = $code; St = $st; Obs = $obs }
}
$ask = "/api/ask/text"
$tests = @(
  (T "T01" "Health check"                 "GET"  "/api/health" $null $null 200 "ok" $false)
  (T "T02" "Valid question: maize"        "POST" $ask @{question="Ni gute nahinga ibigori?"} $null 200 "answered" $false)
  (T "T03" "Valid question: potatoes"     "POST" $ask @{question="Ibirayi bitera mu butaka bumeze bute?"} $null 200 "answered" $false)
  (T "T04" "Valid question: mushrooms"    "POST" $ask @{question="Ni gute nakora ubuhinzi bw'ibihumyo?"} $null 200 "answered" $false)
  (T "T05" "Off-topic: football"          "POST" $ask @{question="Ni nde watwaye igikombe cy'isi cya 2022?"} $null 200 "referred" $false)
  (T "T06" "Gibberish: asdfgh"            "POST" $ask @{question="asdfgh"} $null 200 "referred" $false)
  (T "T07" "Empty question"               "POST" $ask @{question=""} $null 422 "" $false)
  (T "T08" "Spaces only"                  "POST" $ask @{question="   "} $null 200 "referred" $false)
  (T "T09" "Exactly 500 characters"       "POST" $ask @{question=("a" * 500)} $null 200 "" $false)
  (T "T10" "501 characters"               "POST" $ask @{question=("a" * 501)} $null 422 "" $false)
  (T "T11" "Script tag as question"       "POST" $ask @{question="<script>alert(1)</script>"} $null 200 "" $false)
  (T "T12" "Malformed JSON body"          "POST" $ask $null "{bad json" 422 "" $false)
  (T "T13" "Wrong method on ask route"    "GET"  $ask $null $null 404 "" $false)
  (T "T14" "Unknown route"                "GET"  "/api/nope" $null $null 404 "" $true)
  (T "T15" "Feedback, valid"              "POST" "/api/feedback" @{answer_id=-1; rating=5; is_useful=$true; comment="test1"} $null 201 "" $false)
  (T "T16" "Feedback, unknown answer id"  "POST" "/api/feedback" @{answer_id=999999; rating=3; is_useful=$true} $null 404 "" $false)
  (T "T17" "Feedback, rating 6"           "POST" "/api/feedback" @{answer_id=-1; rating=6; is_useful=$true} $null 422 "" $false)
  (T "T18" "Officer queue, no token"      "GET"  "/api/officer/answers" $null $null 401 "" $false)
  (T "T19" "Admin stats, no credentials"  "GET"  "/api/admin/stats" $null $null 401 "" $false)
)

$rows = @()
foreach ($t in $tests) {
  if ($t.B -and $t.B.ContainsKey("answer_id") -and $t.B.answer_id -eq -1) {
    if ($script:aid) { $t.B.answer_id = $script:aid } else { $t.B.answer_id = 1 }
  }
  $r = Call $t.M $t.P $t.B $t.Raw
  if ($t.Id -eq "T02" -and $r.J.answer_id) { $script:aid = [int]$r.J.answer_id }
  $res = "PASS"
  if ($r.Code -ne $t.Code) { $res = "FAIL" }
  elseif ($t.St -and $r.J.status -ne $t.St) { $res = "FAIL" }
  if ($t.Obs) { $res = "OBSERVE" }
  $note = ""; if ($r.Ms -gt 5000) { $note = "SLOW (over 5 s)" }
  $exp = "HTTP $($t.Code)"; if ($t.St) { $exp += " $($t.St)" }
  $rows += [pscustomobject]@{ ID = $t.Id; Test = $t.Name; Expected = $exp; HTTP = $r.Code; Status = $r.J.status
    Reason = $r.J.referral_reason; Score = $r.J.retrieval_score; RoundTripMs = $r.Ms; Result = $res; Note = $note
    Time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
  $c = "Yellow"; if ($res -eq "PASS") { $c = "Green" } elseif ($res -eq "FAIL") { $c = "Red" }
  Write-Host ("[{0}] {1} {2,-30} HTTP {3} {4} {5} {6}ms" -f $res, $t.Id, $t.Name, $r.Code, $r.J.status, $r.J.referral_reason, $r.Ms) -ForegroundColor $c
}

$rows | Export-Csv -Path $file -NoTypeInformation -Encoding UTF8
$pass = @($rows | Where-Object { $_.Result -eq "PASS" }).Count
$fail = @($rows | Where-Object { $_.Result -eq "FAIL" }).Count
$obs  = @($rows | Where-Object { $_.Result -eq "OBSERVE" }).Count
Write-Host "`nSUMMARY: $pass passed, $fail failed, $obs to judge by hand (of $($rows.Count))" -ForegroundColor Cyan
$bad = @($rows | Where-Object { $_.Result -ne "PASS" })
if ($bad.Count -gt 0) { $bad | Select-Object ID, Test, Expected, HTTP, Status, Reason, Result | Format-Table -AutoSize }
Write-Host "Saved: $file" -ForegroundColor Cyan
