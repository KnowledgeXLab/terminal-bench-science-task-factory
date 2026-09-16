$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = (Get-Location).Path
$generated = Join-Path $root 'generated'
$verification = Get-Content -Raw -Encoding UTF8 (Join-Path $generated 'VERIFICATION.json') | ConvertFrom-Json
$selected = @($verification.tasks | Where-Object {
  $id = 0
  [int]::TryParse((([string]$_.candidate_id -split '-')[-1]), [ref]$id) -and $id -ge 201 -and $id -le 400
})
if ($selected.Count -ne 200) { throw "expected 200 batch2 tasks, found $($selected.Count)" }
if (@($selected | Where-Object { $_.status -ne 'validated_local' }).Count -ne 0) { throw 'batch2 contains non-validated task' }
foreach ($entry in $selected) {
  $rewards = @($entry.verification.local_harbor.rewards)
  if ($rewards.Count -eq 0 -or @($rewards | Where-Object { [double]$_ -ne 1.0 }).Count -ne 0) { throw "missing all-1 evidence: $($entry.path)" }
  if (-not (Test-Path (Join-Path $generated $entry.path))) { throw "missing task directory: $($entry.path)" }
}
$selectedIds = @{}
foreach ($entry in $selected) { $selectedIds[[string]$entry.candidate_id] = $true }
$candidateRows = @(Get-Content -Encoding UTF8 (Join-Path $generated 'candidates/next_batch.jsonl') | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $selectedIds.ContainsKey([string]$_.candidate_id) })
if ($candidateRows.Count -ne 200) { throw "expected 200 candidate rows, found $($candidateRows.Count)" }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archivePath = Join-Path $root ("work/terminal-bench-science-new-200-batch2-harbor-verified-$stamp.zip")
$zip = [IO.Compression.ZipFile]::Open($archivePath, [IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($entry in ($selected | Sort-Object path)) {
    $taskRoot = Join-Path $generated $entry.path
    foreach ($file in Get-ChildItem -LiteralPath $taskRoot -Recurse -File) {
      $name = $file.FullName.Substring($generated.Length + 1).Replace('\','/')
      [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $name, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
  }
  $subset = [ordered]@{
    generated_at = $verification.generated_at
    scope = '200 synthetic tasks generated as batch2 (candidate IDs tbds-20260905-0201 through tbds-20260905-0400)'
    backend_note = 'Every selected task has local Harbor Docker oracle reward=1 evidence.'
    docker_harbor_verified = $false
    formal_ecp_gate = [ordered]@{ required = $true; status = 'pending' }
    tasks = @($selected | Sort-Object path)
  }
  $utf8 = New-Object Text.UTF8Encoding($false)
  $e = $zip.CreateEntry('candidates.jsonl'); $w = New-Object IO.StreamWriter($e.Open(),$utf8); foreach ($row in $candidateRows) { $w.WriteLine(($row | ConvertTo-Json -Compress -Depth 30)) }; $w.Dispose()
  $e = $zip.CreateEntry('VERIFICATION.json'); $w = New-Object IO.StreamWriter($e.Open(),$utf8); $w.WriteLine(($subset | ConvertTo-Json -Depth 30)); $w.Dispose()
  $readme = @'
# Terminal-Bench Science — batch2 Harbor-verified delivery

This archive contains exactly 200 synthetic Terminal-Bench Science task directories from batch2 (candidate IDs `tbds-20260905-0201` through `tbds-20260905-0400`). Each task includes its instruction, task metadata, generated environment/data, oracle solution, and independent verifier tests.

All selected tasks were executed through the local Docker Desktop Harbor environment with the `oracle` agent and have recorded verifier reward `1`. Formal ECP/CCR cluster verification is not claimed; `docker_harbor_verified` remains false until that separate gate is run.

The archive excludes factory source code, API credentials, `.env`, jobs, caches, and Docker images.
'@
  $e = $zip.CreateEntry('README.md'); $w = New-Object IO.StreamWriter($e.Open(),$utf8); $w.Write($readme); $w.Dispose()
}
finally { $zip.Dispose() }
$check = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
  $names = @($check.Entries | ForEach-Object FullName)
  $instructions = @($names | Where-Object { $_ -like '*/instruction.md' })
  $tests = @($names | Where-Object { $_ -like '*/tests/test.sh' })
  $forbidden = @($names | Where-Object { $_ -eq '.env' -or $_ -like 'jobs/*' -or $_ -like 'work/*' -or $_ -like 'tb_science_factory/*' })
  if ($instructions.Count -ne 200 -or $tests.Count -ne 200 -or $forbidden.Count -ne 0) { throw "archive checks failed: instructions=$($instructions.Count), tests=$($tests.Count), forbidden=$($forbidden.Count)" }
  foreach ($n in $names) {
    if ($n -notlike '*/' -and $n -notin @('README.md','VERIFICATION.json','candidates.jsonl')) {
      $entry = $check.GetEntry($n); $sr = New-Object IO.StreamReader($entry.Open()); $content = $sr.ReadToEnd(); $sr.Dispose()
      if ($content -match '(?i)(OPENAI_API_KEY|Authorization:\s*Bearer|sk-[A-Za-z0-9])') { throw "possible secret in $n" }
    }
  }
}
finally { $check.Dispose() }
[pscustomobject]@{ archive = $archivePath; bytes = (Get-Item $archivePath).Length; tasks = 200; instructions = 200; tests = 200; formal_ecp_pending = $true } | ConvertTo-Json -Compress
