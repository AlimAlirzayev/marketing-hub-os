$ErrorActionPreference = 'Stop'

$deckDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$slideOne = Join-Path $deckDir 'render-1.png'
$slideTwo = Join-Path $deckDir 'render-2.png'
$pptxPath = Join-Path $deckDir 'Powerbank-Qerar-YENI.pptx'
$pdfPath = Join-Path $deckDir 'Powerbank-Qerar-YENI.pdf'

function Add-ClickArea {
    param($Slide, [double]$Left, [double]$Top, [double]$Width, [double]$Height, [string]$Url)
    $shape = $Slide.Shapes.AddShape(1, $Left, $Top, $Width, $Height)
    $shape.Fill.ForeColor.RGB = 0xFFFFFF
    $shape.Fill.Transparency = 0.99
    $shape.Line.Transparency = 1
    $shape.ActionSettings.Item(1).Action = 7
    $shape.ActionSettings.Item(1).Hyperlink.Address = $Url
}

$powerPoint = $null
$presentation = $null
try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $powerPoint.DisplayAlerts = 1
    $presentation = $powerPoint.Presentations.Add()
    $presentation.PageSetup.SlideWidth = 960
    $presentation.PageSetup.SlideHeight = 540

    $first = $presentation.Slides.Add(1, 12)
    $null = $first.Shapes.AddPicture($slideOne, 0, -1, 0, 0, 960, 540)

    $second = $presentation.Slides.Add(2, 12)
    $null = $second.Shapes.AddPicture($slideTwo, 0, -1, 0, 0, 960, 540)

    # Buying buttons on slide 2. Pixel coordinates from the validated 1600x900 render, scaled by 0.6.
    $buyLinks = @(
        @{L=561; T=285; W=174; H=23; U='https://birmarket.az/product/889612-xarici-akkumulyator-xiaomi-bhr5080cn-20000-mah-black'},
        @{L=740; T=285; W=174; H=23; U='https://birmarket.az/product/177584-xarici-akkumulyator-xiaomi-redmi-18w-power-bank-20000mah-qara'},
        @{L=561; T=312; W=174; H=23; U='https://www.bakuelectronics.az/mehsul/power-bank-xiaomi-redmi-18w-fast-charge-20000mah-black-pb200lzm-177482'},
        @{L=740; T=312; W=174; H=23; U='https://bakuelectronics.az/mehsul/xiaomi-67w-power-bank-20000-integrated-cable-tan-pb2067-224057'},
        @{L=561; T=339; W=174; H=23; U='https://us.ugreen.com/products/ugreen-25w-magnetic-power-bank-10000mah'},
        @{L=740; T=339; W=174; H=23; U='https://birmarket.az/product/2033750-powerbank-baseus-magnetic-mini-10000mah-30w-white'}
    )
    foreach ($link in $buyLinks) { Add-ClickArea -Slide $second -Left $link.L -Top $link.T -Width $link.W -Height $link.H -Url $link.U }

    $sourceLinks = @(
        @{T=371; U='https://www.mi.com/global/product/mi-50w-power-bank-20000/specs/'},
        @{T=383; U='https://rozetka.com.ua/ua/xiaomi-bhr5121gl/p334607548/comments/'},
        @{T=395; U='https://www.mi.com/uk/product/xiaomi-67w-power-bank-20000-integrated-cable/specs/'},
        @{T=407; U='https://www.macworld.com/article/2915110/ugreen-25w-magflow-magnetic-wireless-10k-power-bank-review-leader-of-the-pack.html'}
    )
    foreach ($link in $sourceLinks) { Add-ClickArea -Slide $second -Left 561 -Top $link.T -Width 350 -Height 10 -Url $link.U }

    $presentation.SaveAs($pptxPath, 24)
    $presentation.SaveAs($pdfPath, 32)
}
finally {
    if ($presentation) { $presentation.Close() }
    if ($powerPoint) { $powerPoint.Quit() }
    if ($presentation) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) }
    if ($powerPoint) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Get-Item $pptxPath, $pdfPath | Select-Object FullName, Length, LastWriteTime
