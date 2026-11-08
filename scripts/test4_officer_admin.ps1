$base = "https://mfasha-chatbot.vercel.app/mfasha"
$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root "results\system_testing"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$file = Join-Path $out "test4_officer_admin.csv"

$sec  = Read-Host "Officer sign-up code (hidden, never saved)" -AsSecureString
$code = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$phone = "0788" + (Get-Random -Minimum 100000 -Maximum 999999)
$pin = "4829"; $badpin = "1111"
$rows = @()

function Call($method, $path, $body, $token, $apikey) {
  $p = @{ Uri = "$base$path"; Method = $method; UseBasicParsing = $true; TimeoutSec = 60 }
  $h = @{}
  if ($token)  { $h["Authorization"] = "Bearer $token" }
  if ($apikey) { $h["X-API-Key"] = $apikey }
  if ($h.Count -gt 0) { $p.Headers = $h }
  if ($body) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress)); $p.ContentType = "application/json; charset=utf-8" }
  $sw = [Diagnostics.Stopwatch]::StartNew(); $c = 0; $j = $null; $detail = ""
  try {
    $r = Invoke-WebRequest @p; $c = [int]$r.StatusCode
    try { $j = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json } catch { $j = $null }
  } catch {
    if ($_.Exception.Response) {
      $c = [int]$_.Exception.Response.StatusCode
      try { $e = $_.ErrorDetails.Message | ConvertFrom-Json; $detail = "$($e.detail)" } catch { $detail = "" }
    } else { $c = -1 }
  }
  [pscustomobject]@{ Code = $c; J = $j; Detail = $detail; Ms = [int]$sw.Elapsed.TotalMilliseconds }
}

function Rec($id, $name, $exp, $c, $ms, $res, $note) {
  $script:rows += [pscustomobject]@{ ID = $id; Test = $name; Expected = $exp; HTTP = $c; RoundTripMs = $ms; Result = $res; Note = $note; Time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
  $col = "Yellow"; if ($res -eq "PASS") { $col = "Green" } elseif ($res -eq "FAIL") { $col = "Red" }
  Write-Host ("[{0}] {1} {2,-46} HTTP {3} {4}ms {5}" -f $res, $id, $name, $c, $ms, $note) -ForegroundColor $col
}
function Chk($id, $name, $r, $exp, $note) {
  $res = "FAIL"; if ($r.Code -eq $exp) { $res = "PASS" }
  Rec $id $name "HTTP $exp" $r.Code $r.Ms $res $note
}
function Finish {
  $rows | Export-Csv -Path $file -NoTypeInformation -Encoding UTF8
  $pass = @($rows | Where-Object { $_.Result -eq "PASS" }).Count
  $fail = @($rows | Where-Object { $_.Result -eq "FAIL" }).Count
  $obs  = @($rows | Where-Object { $_.Result -eq "OBSERVE" }).Count
  Write-Host "`nSUMMARY: $pass passed, $fail failed, $obs to judge by hand (of $($rows.Count))" -ForegroundColor Cyan
  $bad = @($rows | Where-Object { $_.Result -ne "PASS" })
  if ($bad.Count -gt 0) { $bad | Select-Object ID, Test, Expected, HTTP, Result, Note | Format-Table -AutoSize }
  Write-Host "Test officer phone $phone stays on the app until the Space restarts."
  Write-Host "Saved: $file" -ForegroundColor Cyan
}

# setup: one real answer to review later
$q = Call "POST" "/api/ask/text" @{ question = "Ni gute nahinga ibigori?" } $null $null
$aid = $q.J.answer_id
if (-not $aid) { Write-Host "Could not create a test answer. Is the app up?" -ForegroundColor Red; return }

# --- registration
$r = Call "POST" "/api/officer/register" @{ name = "Test Officer"; phone = $phone; pin = $pin; code = "wrong-code-test" } $null $null
Chk "O01" "Register with a wrong sign-up code" $r 401 ""
$r = Call "POST" "/api/officer/register" @{ name = "Test Officer"; phone = $phone; pin = $pin; code = $code } $null $null
Chk "O02" "Register with the correct sign-up code" $r 201 ""
if ($r.Code -eq 503) { Write-Host "Sign-up is closed: MFASHA_OFFICER_CODE is not set on the Space." -ForegroundColor Red; Finish; return }
if ($r.Code -ne 201) { Write-Host "The sign-up code was rejected, so the later tests cannot run." -ForegroundColor Red; Finish; return }
$token = $r.J.token
$r = Call "POST" "/api/officer/register" @{ name = "Test Officer"; phone = $phone; pin = $pin; code = $code } $null $null
Chk "O03" "Register the same phone number twice" $r 409 ""
$r = Call "POST" "/api/officer/register" @{ name = "Test Officer"; phone = "0788111222"; pin = "12"; code = $code } $null $null
Chk "O04" "Register with a 2-digit PIN" $r 422 ""

# --- login
$r = Call "POST" "/api/officer/login" @{ phone = $phone; pin = $pin } $null $null
$res = "FAIL"; if ($r.Code -eq 200 -and $r.J.token) { $res = "PASS" }
Rec "O05" "Login with the correct PIN" "HTTP 200 + token" $r.Code $r.Ms $res ""
$wrong = Call "POST" "/api/officer/login" @{ phone = $phone; pin = $badpin } $null $null
Chk "O06" "Login with a wrong PIN" $wrong 401 ""
$unk = Call "POST" "/api/officer/login" @{ phone = "0788999888"; pin = $pin } $null $null
$res = "FAIL"; if ($unk.Code -eq 401 -and $unk.Detail -eq $wrong.Detail -and $wrong.Detail) { $res = "PASS" }
Rec "O07" "Unknown phone gives the same message as wrong PIN" "HTTP 401, same text" $unk.Code $unk.Ms $res "does not reveal which numbers have accounts"

# --- what an officer can do
$r = Call "GET" "/api/officer/answers" $null $token $null
Chk "O08" "Officer queue with a valid token" $r 200 ""
$rev = @{ answer_id = $aid; reviewer = "Someone Else"; verdict = "correct"; is_relevant = $true; is_clear = $true; is_safe = $true; remarks = "system test" }
$r = Call "POST" "/api/officer/reviews" $rev $token $null
Chk "O09" "Submit a valid review" $r 201 ""
$bad = @{ answer_id = $aid; reviewer = "Test Officer"; verdict = "maybe"; is_relevant = $true; is_clear = $true; is_safe = $true }
$r = Call "POST" "/api/officer/reviews" $bad $token $null
Chk "O10" "Review with verdict 'maybe'" $r 422 ""
$unkrev = @{ answer_id = 999999; reviewer = "Test Officer"; verdict = "correct"; is_relevant = $true; is_clear = $true; is_safe = $true }
$r = Call "POST" "/api/officer/reviews" $unkrev $token $null
Chk "O11" "Review an unknown answer id" $r 404 ""
$r = Call "POST" "/api/officer/reviews" $rev $null $null
Chk "O12" "Review with no token" $r 401 ""
$r = Call "GET" "/api/officer/answers" $null "abc.def.ghi" $null
Chk "O13" "Garbage token" $r 401 ""
$r = Call "GET" "/api/officer/answers" $null ($token + "x") $null
Chk "O14" "Tampered token" $r 401 ""
$r = Call "GET" "/api/officer/answers?unreviewed=true&limit=200" $null $token $null
$ids = @($r.J | ForEach-Object { $_.answer_id })
$res = "FAIL"; if ($r.Code -eq 200 -and ($ids -notcontains $aid)) { $res = "PASS" }
Rec "O15" "Reviewed answer leaves the unreviewed queue" "answer not in queue" $r.Code $r.Ms $res "answer_id $aid"

# --- admin stats
$r = Call "GET" "/api/admin/stats" $null $token $null
$res = "FAIL"; if ($r.Code -eq 200 -and $r.J.questions -ge 1) { $res = "PASS" }
Rec "O16" "Stats with an officer token" "HTTP 200 + counts" $r.Code $r.Ms $res ("questions " + $r.J.questions)
$res = "FAIL"; if ($r.Code -eq 200 -and $r.J.expert_reviews -ge 1) { $res = "PASS" }
Rec "O17" "Stats count the new review" "expert_reviews >= 1" $r.Code $r.Ms $res ("expert_reviews " + $r.J.expert_reviews)
$r = Call "GET" "/api/admin/stats" $null $null "wrong-key-test"
$res = "FAIL"; $note = ""
if ($r.Code -eq 401) { $res = "PASS" } elseif ($r.Code -eq 503) { $res = "OBSERVE"; $note = "API key access is switched off on this Space" }
Rec "O18" "Stats with a wrong API key" "HTTP 401" $r.Code $r.Ms $res $note

# --- lockout last: it locks the test officer for 5 minutes
$codes = @()
for ($i = 1; $i -le 4; $i++) { $x = Call "POST" "/api/officer/login" @{ phone = $phone; pin = $badpin } $null $null; $codes += $x.Code }
$r = Call "POST" "/api/officer/login" @{ phone = $phone; pin = $pin } $null $null
$res = "FAIL"; if ($r.Code -eq 429) { $res = "PASS" }
Rec "O19" "Locked after 5 wrong PINs (even the right PIN)" "HTTP 429" $r.Code $r.Ms $res ("wrong attempts returned " + ($codes -join ","))

Finish
