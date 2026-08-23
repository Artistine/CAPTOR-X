# clean_mei_temp.ps1
# Run this script in PowerShell to clean up orphaned PyInstaller temp folders on your C drive.

$TempPath = [System.IO.Path]::GetTempPath()
$MeiFolders = Get-ChildItem -Path $TempPath -Filter "_MEI*" -Directory

if ($MeiFolders.Count -eq 0) {
    Write-Host "No _MEI temporary folders found in $TempPath." -ForegroundColor Green
    exit
}

Write-Host "Found $($MeiFolders.Count) _MEI temporary folder(s) in $TempPath." -ForegroundColor Yellow
$FreedSpaceBytes = 0

foreach ($Folder in $MeiFolders) {
    $FolderPath = $Folder.FullName
    try {
        # Calculate size before deleting
        $Size = (Get-ChildItem -Path $FolderPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
        if ($Size -eq $null) { $Size = 0 }
        
        # Try to delete the folder (will fail if in use/locked by a running app)
        Remove-Item -Path $FolderPath -Recurse -Force -ErrorAction Stop
        $FreedSpaceBytes += $Size
        Write-Host "Successfully deleted: $FolderPath ($([Math]::Round($Size / 1MB, 2)) MB)" -ForegroundColor Green
    }
    catch {
        Write-Host "Skipped (currently in use by a running process): $FolderPath" -ForegroundColor Gray
    }
}

$FreedSpaceMB = [Math]::Round($FreedSpaceBytes / 1MB, 2)
$FreedSpaceGB = [Math]::Round($FreedSpaceBytes / 1GB, 2)

if ($FreedSpaceBytes -gt 0) {
    Write-Host "`nCleanup completed! Freed approximately $FreedSpaceMB MB ($FreedSpaceGB GB) on your C drive." -ForegroundColor Green
} else {
    Write-Host "`nNo folders were deleted because they are all currently in use." -ForegroundColor Yellow
}
