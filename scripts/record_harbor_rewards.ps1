$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$verificationPath = Join-Path $root 'generated/VERIFICATION.json'
$candidatesPath = Join-Path $root 'generated/candidates/next_batch.jsonl'
$nextPath = Join-Path $root 'generated/NEXT_BATCH.json'
$verification = Get-Content -Raw -Encoding UTF8 $verificationPath | ConvertFrom-Json
$candidateRows = @(Get-Content -Encoding UTF8 $candidatesPath | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
$entries = @{}
foreach ($entry in $verification.tasks) { $entries[[string]$entry.path] = $entry }
$evidence = @{}
$jobsRoot = Join-Path $root 'jobs'
if (Test-Path $jobsRoot) {
  Get-ChildItem -Path $jobsRoot -Recurse -File -Filter 'reward.txt' | Where-Object { $_.Directory.Name -eq 'verifier' } | ForEach-Object {
    try { $reward = [double](Get-Content -Raw -Encoding UTF8 $_.FullName).Trim() } catch { return }
    if ($reward -ne 1.0) { return }
    $trialDir = $_.Directory.Parent
    $resultPath = Join-Path $trialDir.FullName 'result.json'
    if (-not (Test-Path $resultPath)) { return }
    try { $result = Get-Content -Raw -Encoding UTF8 $resultPath | ConvertFrom-Json } catch { return }
    $rawPath = [string]$result.task_id.path
    if (-not $rawPath) { return }
    $taskPath = $rawPath.Replace('\','/')
    if ($taskPath.StartsWith('generated/tasks/')) { $taskPath = 'tasks/' + $taskPath.Substring('generated/tasks/'.Length) }
    elseif ($taskPath -match '/generated/tasks/') { $taskPath = 'tasks/' + ($taskPath -split '/generated/tasks/',2)[1] }
    if ($entries.ContainsKey($taskPath) -and -not $evidence.ContainsKey($taskPath)) {
      $evidence[$taskPath] = $trialDir.Parent.FullName.Substring($root.Length + 1).Replace('\','/')
    }
  }
}
$promoted = 0
foreach ($taskPath in $evidence.Keys) {
  $entry = $entries[$taskPath]
  if ([string]$entry.status -ne 'validated_local') { $promoted++ }
  $jobRel = $evidence[$taskPath]
  $slug = [string]$entry.slug
  $verificationObj = [pscustomobject]@{
    reward = 1
    oracle_exit_code = 0
    tests_exit_code = 0
    backend = 'Harbor Docker on local Docker Desktop'
    docker_harbor_verified = $false
    local_harbor = [pscustomobject]@{
      backend = 'harbor/docker on local Docker Desktop'
      oracle_trials = 1
      rewards = @(1)
      jobs_result = ($jobRel + '/result.json')
    }
  }
  $entry.status = 'validated_local'
  $entry.verification = $verificationObj
  foreach ($row in $candidateRows) {
    if ([string]$row.materialized_path -eq $taskPath) {
      $row.status = 'validated_local'
      $row | Add-Member -MemberType NoteProperty -Name verification -Value $verificationObj -Force
    }
  }
}
$verification.tasks = @($entries.Values | Sort-Object path)
$verificationText = $verification | ConvertTo-Json -Depth 30
[IO.File]::WriteAllText($verificationPath, $verificationText + "`n", (New-Object Text.UTF8Encoding($false)))
$candidateText = (($candidateRows | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 30 }) -join "`n") + "`n"
[IO.File]::WriteAllText($candidatesPath, $candidateText, (New-Object Text.UTF8Encoding($false)))
$next = Get-Content -Raw -Encoding UTF8 $nextPath | ConvertFrom-Json
$validated = @($verification.tasks | Where-Object { $_.status -eq 'validated_local' }).Count
$valid = @($candidateRows | Where-Object { -not $_.validation_errors }).Count
$next.validated_local_count = $validated
$next.valid_candidate_count = $valid
$next.formal_ecp_pending_count = $valid - $validated
[IO.File]::WriteAllText($nextPath, (($next | ConvertTo-Json -Depth 20) + "`n"), (New-Object Text.UTF8Encoding($false)))
[pscustomobject]@{ new_harbor_tasks = $promoted; validated_local_count = $validated; formal_ecp_pending_count = ($valid - $validated) } | ConvertTo-Json -Compress
