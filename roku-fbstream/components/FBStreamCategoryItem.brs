sub init()
    m.categoryLabel = m.top.findNode("categoryLabel")
end sub

sub showContent()
    content = m.top.itemContent
    if content <> invalid
        m.categoryLabel.text = content.title
    end if
end sub