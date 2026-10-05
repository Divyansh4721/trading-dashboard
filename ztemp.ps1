# Define your input files and output path
$files = @(
    "app.py",
    "breeze_core.py",
    "holdings_page.py",
    "delivery_page.py",
    "mtf_page.py",
    "trade_page.py"
)

$outputFile = "combined_output.txt"

# Clear existing output file if it exists
if (Test-Path $outputFile) {
    Remove-Item $outputFile
}

# Loop through each file and append the formatted content
foreach ($file in $files) {
    if (Test-Path $file) {
        # Write the filename header
        Add-Content -Path $outputFile -Value "=== $file ==="
        
        # Append the file content
        Get-Content -Path $file | Add-Content -Path $outputFile
        
        # Add spacing between files
        Add-Content -Path $outputFile -Value "`n"
    } else {
        Write-Warning "File not found: $file"
    }
}

Write-Host "Successfully generated $outputFile" -ForegroundColor Green