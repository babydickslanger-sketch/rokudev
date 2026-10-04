sub init()
    m.categoryLabel = m.top.findNode("categoryLabel")
    m.categoryBackground = m.top.findNode("categoryBackground")
end sub

sub showContent()
    content = m.top.itemContent
    if content <> invalid and m.categoryLabel <> invalid
        m.categoryLabel.text = content.title
    end if
end sub
