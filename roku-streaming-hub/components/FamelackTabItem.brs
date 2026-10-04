sub init()
    m.tabLabel = m.top.findNode("tabLabel")
    m.tabBackground = m.top.findNode("tabBackground")
end sub

sub showContent()
    content = m.top.itemContent
    if content <> invalid and m.tabLabel <> invalid
        m.tabLabel.text = content.title
    end if
end sub
