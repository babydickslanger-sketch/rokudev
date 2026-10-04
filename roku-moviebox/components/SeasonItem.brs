sub init()
    m.seasonLabel = m.top.findNode("seasonLabel")
    m.seasonBackground = m.top.findNode("seasonBackground")
end sub

sub showContent()
    content = m.top.itemContent
    if content <> invalid and m.seasonLabel <> invalid
        m.seasonLabel.text = content.title
    end if
end sub
