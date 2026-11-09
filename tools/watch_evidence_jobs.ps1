<#
.SYNOPSIS
Shows live progress from the local evidence runner's saved reports.
.PARAMETER JobsRoot
Directory containing job folders. Defaults to artifacts/maintenance/jobs.
.PARAMETER Snapshot
Prints one JSON snapshot without opening a window.
#>
[CmdletBinding()]
param(
    [string]$JobsRoot,
    [ValidateRange(1, 60)][int]$RefreshSeconds = 2,
    [switch]$Snapshot,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$artifactRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../artifacts'))
if (!$JobsRoot) { $JobsRoot = Join-Path $artifactRoot 'maintenance/jobs' }
$JobsRoot = [IO.Path]::GetFullPath($JobsRoot)

function Read-JobJson([string]$Path) {
    try {
        if ([IO.File]::Exists($Path)) {
            return [IO.File]::ReadAllText($Path) | ConvertFrom-Json
        }
    } catch [IO.IOException] {
        # The runner can atomically replace a report while we read it.
    } catch [ArgumentException] {
        # A report from an older or interrupted producer may be unreadable.
    }
}

function Test-Worker([int]$WorkerId, [double]$Started) {
    if ($WorkerId -le 0) { return $false }
    $process = Get-Process -Id $WorkerId -ErrorAction SilentlyContinue
    if (!$process) { return $false }
    try {
        $birth = ([DateTimeOffset]$process.StartTime).ToUnixTimeSeconds()
        # Avoid mistaking a recycled PID for the original supervisor.
        return $birth -le ($Started + 2) -and $birth -ge ($Started - 60)
    } catch {
        return $true
    }
}

function Get-PhaseProgress($Planned, $Passed, [string]$Phase) {
    return [pscustomobject]@{
        Done = @($Passed | Where-Object phase -eq $Phase).Count
        Total = @($Planned | Where-Object phase -eq $Phase).Count
    }
}

function Get-Jobs {
    if (!(Test-Path -LiteralPath $JobsRoot -PathType Container)) { return }
    foreach ($directory in Get-ChildItem -LiteralPath $JobsRoot -Directory) {
        $report = Read-JobJson (Join-Path $directory.FullName 'report.json')
        $launch = Read-JobJson (Join-Path $directory.FullName 'launch.json')
        if (!$report -and !$launch) { continue }
        $status = [string]$report.status
        $started = [double]$report.started
        if ($launch -and (!$report -or
                ($launch.started -gt $report.started -and $launch.pid -ne $report.pid))) {
            $started = [double]$launch.started
            $status = if (Test-Worker $launch.pid $started) { 'starting' } else { 'interrupted' }
            $report = $null
        } elseif ($status -eq 'running' -and !(Test-Worker $report.pid $started)) {
            $status = 'interrupted'
        }
        $plan = Read-JobJson (Join-Path $directory.FullName 'plan.json')
        $planned = @($plan.steps | Where-Object { $_ -and $report })
        $steps = @($report.steps | Where-Object { $_ })
        $passed = @($steps | Where-Object {
            $_.attempts.Count -gt 0 -and
            $_.attempts[-1].exit_code -eq 0 -and !$_.attempts[-1].reason
        })
        $current = @($planned | Where-Object id -eq $report.current_step | Select-Object -First 1)
        $elapsed = if ($null -ne $report.elapsed_s) { $report.elapsed_s } else {
            $until = if ($status -eq 'interrupted') {
                $reportFile = Get-Item -LiteralPath (Join-Path $directory.FullName 'report.json') -ErrorAction SilentlyContinue
                $lastWrite = if ($reportFile) { $reportFile.LastWriteTimeUtc } else { $directory.LastWriteTimeUtc }
                ([DateTimeOffset]$lastWrite).ToUnixTimeSeconds()
            } else { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
            [math]::Max(0, $until - $started)
        }
        $diagnostic = [string]$report.error
        if (!$diagnostic -and $status -eq 'failed' -and $steps.Count) {
            $attempt = $steps[-1].attempts[-1]
            $diagnostic = (@($attempt.reason, $attempt.diagnostic) | Where-Object { $_ }) -join [Environment]::NewLine
        }
        [pscustomobject]@{
            Name = $directory.Name
            Folder = $directory.FullName
            Status = $status
            Started = $started
            ElapsedSeconds = [int][math]::Floor($elapsed)
            Step = [string]$report.current_step
            Phase = if ($current.Count) { [string]$current[0].phase } else { '' }
            Passed = $passed.Count
            Total = if ($report) { $planned.Count } else { 0 }
            Numeric = Get-PhaseProgress $planned $passed 'numeric'
            Render = Get-PhaseProgress $planned $passed 'render'
            RenderReused = [int]$report.case_counts.reused
            ReviewIndex = @($report.review_indexes | Where-Object { $_ } | Select-Object -Last 1) -join ''
            Diagnostic = $diagnostic.Trim()
        }
    }
}

function Get-SortedJobs {
    Get-Jobs | Sort-Object @{ Expression = { $_.Status -in @('running', 'starting') }; Descending = $true },
                          @{ Expression = 'Started'; Descending = $true }
}

if ($Snapshot) {
    ConvertTo-Json -InputObject @(Get-SortedJobs) -Depth 4
    return
}

if ([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') {
    throw 'Open with powershell.exe -NoProfile -STA -File tools/watch_evidence_jobs.ps1'
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

$form = [Windows.Forms.Form]::new()
$form.Text = 'Blender Evidence Runner'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = [Drawing.Size]::new(620, 370)
$form.MinimumSize = [Drawing.Size]::new(560, 360)
$form.Font = [Drawing.Font]::new('Segoe UI', 10)

$layout = [Windows.Forms.TableLayoutPanel]::new()
$layout.Dock = 'Fill'
$layout.Padding = [Windows.Forms.Padding]::new(16)
$layout.ColumnCount = 1
$layout.RowCount = 8
foreach ($row in 1..7) {
    $layout.RowStyles.Add([Windows.Forms.RowStyle]::new([Windows.Forms.SizeType]::AutoSize)) | Out-Null
}
$layout.RowStyles.Add([Windows.Forms.RowStyle]::new([Windows.Forms.SizeType]::Percent, 100)) | Out-Null
$form.Controls.Add($layout)

$picker = [Windows.Forms.ComboBox]::new()
$picker.DropDownStyle = 'DropDownList'
$picker.Dock = 'Top'
$layout.Controls.Add($picker)

function Add-ProgressLabel {
    $label = [Windows.Forms.Label]::new()
    $label.AutoSize = $true
    $label.Margin = [Windows.Forms.Padding]::new(3, 6, 3, 3)
    $layout.Controls.Add($label)
    return $label
}

$statusLabel = Add-ProgressLabel
$statusLabel.Font = [Drawing.Font]::new('Segoe UI Semibold', 14)
$stepLabel = Add-ProgressLabel
$bar = [Windows.Forms.ProgressBar]::new()
$bar.Dock = 'Top'
$bar.Height = 18
$layout.Controls.Add($bar)
$countsLabel = Add-ProgressLabel
$phaseLabel = Add-ProgressLabel

$buttons = [Windows.Forms.FlowLayoutPanel]::new()
$buttons.AutoSize = $true
$layout.Controls.Add($buttons)
$folderButton = [Windows.Forms.Button]::new()
$folderButton.Text = 'Open job folder'
$folderButton.AutoSize = $true
$buttons.Controls.Add($folderButton)
$reviewButton = [Windows.Forms.Button]::new()
$reviewButton.Text = 'Open review folder'
$reviewButton.AutoSize = $true
$buttons.Controls.Add($reviewButton)

$details = [Windows.Forms.TextBox]::new()
$details.Multiline = $true
$details.ReadOnly = $true
$details.ScrollBars = 'Vertical'
$details.Dock = 'Fill'
$layout.Controls.Add($details)

$auto = 'Follow newest active job'
$picker.Items.Add($auto) | Out-Null
$picker.SelectedIndex = 0
$state = @{ Job = $null }

function Get-ReviewPath($Job) {
    if (!$Job.ReviewIndex) { return }
    try {
        $path = [IO.Path]::GetFullPath($Job.ReviewIndex)
        if ($path.StartsWith($artifactRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and
                [IO.Path]::GetFileName($path) -eq 'review-index.json' -and [IO.File]::Exists($path)) {
            return $path
        }
    } catch [ArgumentException] {}
}

function Update-Window {
    $jobs = @(Get-SortedJobs)
    $names = @($auto) + @($jobs | ForEach-Object Name)
    $selection = [string]$picker.SelectedItem
    if ((@($picker.Items) -join '|') -ne ($names -join '|')) {
        $picker.BeginUpdate()
        $picker.Items.Clear()
        $picker.Items.AddRange([object[]]$names)
        $picker.SelectedIndex = [math]::Max(0, [array]::IndexOf($names, $selection))
        $picker.EndUpdate()
    }
    $job = if ($picker.SelectedIndex -eq 0) { $jobs | Select-Object -First 1 } else {
        $jobs | Where-Object Name -eq $picker.SelectedItem | Select-Object -First 1
    }
    $state.Job = $job
    $folderButton.Enabled = [bool]$job
    $reviewButton.Enabled = [bool](Get-ReviewPath $job)
    if (!$job) {
        $statusLabel.Text = 'Waiting for an evidence job'
        $stepLabel.Text = $JobsRoot
        $bar.Value = 0
        $countsLabel.Text = $phaseLabel.Text = $details.Text = ''
        return
    }
    $statusLabel.Text = $job.Status.Replace('_', ' ').ToUpperInvariant() + '  |  ' + $job.Name
    $statusLabel.ForeColor = switch ($job.Status) {
        'completed' { [Drawing.Color]::DarkGreen }
        'needs_review' { [Drawing.Color]::DarkGoldenrod }
        { $_ -in @('failed', 'interrupted') } { [Drawing.Color]::Firebrick }
        default { [Drawing.Color]::MidnightBlue }
    }
    $stepLabel.Text = "Step  $($job.Step)"
    $bar.Maximum = [math]::Max(1, $job.Total)
    $bar.Value = [math]::Min($job.Passed, $bar.Maximum)
    $countsLabel.Text = "Steps  $($job.Passed)/$($job.Total)    Numeric  $($job.Numeric.Done)/$($job.Numeric.Total)    Render  $($job.Render.Done)/$($job.Render.Total)    Reused renders  $($job.RenderReused)"
    $phaseLabel.Text = "Phase  $($job.Phase)    Elapsed  $([TimeSpan]::FromSeconds($job.ElapsedSeconds).ToString('hh\:mm\:ss'))"
    $message = switch ($job.Status) {
        'needs_review' { 'Rendered evidence is ready for inspection. The runner is stopped at its review gate.' }
        'failed' { $job.Diagnostic }
        'interrupted' { 'The saved report shows unfinished work and its supervisor is no longer active.' }
        'completed' { 'This job passed all of its configured steps.' }
        default { 'Progress updates at step boundaries. A render step can contain many Blender frames.' }
    }
    if ($details.Text -ne $message) { $details.Text = $message }
}

$folderButton.Add_Click({ if ($state.Job) { Invoke-Item -LiteralPath $state.Job.Folder } })
$reviewButton.Add_Click({
    $path = Get-ReviewPath $state.Job
    if ($path) { Invoke-Item -LiteralPath ([IO.Path]::GetDirectoryName($path)) }
})
$picker.Add_SelectionChangeCommitted({ Update-Window })
$timer = [Windows.Forms.Timer]::new()
$timer.Interval = $RefreshSeconds * 1000
$timer.Add_Tick({
    Update-Window
    if ($SmokeTest) { $form.Close() }
})
$form.Add_Shown({
    Update-Window
    $timer.Start()
})
try {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($JobsRoot.TrimEnd('\', '/').ToUpperInvariant())))
    } finally {
        $sha.Dispose()
    }
    $created = $false
    $mutex = [Threading.Mutex]::new($true, "Local\BlenderEvidenceViewer-$key", [ref]$created)
    try {
        if ($created) { [void]$form.ShowDialog() }
    } finally {
        if ($created) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
} finally {
    $timer.Dispose()
    $form.Dispose()
}
