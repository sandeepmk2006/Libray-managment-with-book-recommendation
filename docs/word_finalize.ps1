# Opens the report in Microsoft Word, refreshes the table of contents and fields,
# saves the .docx and exports a PDF next to it.
param([string]$Docx)
$path = (Resolve-Path $Docx).Path
$pdf = [System.IO.Path]::ChangeExtension($path, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($path, $false, $false)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)   # 17 = wdExportFormatPDF
    "pages: " + $doc.ComputeStatistics(2)
    $doc.Close($false)
} finally {
    $word.Quit()
}
