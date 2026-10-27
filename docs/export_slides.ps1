# Exports every slide of a .pptx to PNG images using Microsoft PowerPoint.
param([string]$Pptx, [string]$OutDir, [int]$Width = 1600)
$path = (Resolve-Path $Pptx).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$out = (Resolve-Path $OutDir).Path
$app = New-Object -ComObject PowerPoint.Application
try {
    $deck = $app.Presentations.Open($path, $true, $false, $false)   # read-only, no window
    $h = [int]($Width * $deck.PageSetup.SlideHeight / $deck.PageSetup.SlideWidth)
    foreach ($slide in $deck.Slides) {
        $slide.Export((Join-Path $out ("slide{0:D2}.png" -f $slide.SlideIndex)), "PNG", $Width, $h)
    }
    "exported " + $deck.Slides.Count
    $deck.Close()
} finally {
    $app.Quit()
}
