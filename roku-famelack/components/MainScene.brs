sub Init()
    m.tabList = m.top.findNode("tabList")
    m.mediaGrid = m.top.findNode("mediaGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    
    ' Set backend IP - update this to match your server
    m.backendIp = "http://192.168.1.46:8000"
    
    ' Current content type: tv, radio, or webcam
    m.currentContentType = "tv"
    
    ' Setup tabs
    setupTabs()
    
    ' Observe events
    m.tabList.observeField("itemSelected", "onTabSelected")
    m.mediaGrid.observeField("itemSelected", "onItemSelected")
    m.videoPlayer.observeField("state", "onVideoState")
    
    ' Load initial content
    loadCatalog("tv")
end sub

sub setupTabs()
    content = CreateObject("roSGNode", "ContentNode")
    imageIndex = 1
    
    tabData = [
        {title: "Live TV", contentType: "tv"},
        {title: "Radio", contentType: "radio"},
        {title: "Webcams", contentType: "webcam"}
    ]
    
    for each item in tabData
        node = content.CreateChild("ContentNode")
        node.title = item.title
        node.addField("contentType", "string", false)
        node.contentType = item.contentType
    end for
    
    m.tabList.content = content
    m.tabList.setFocus(true)
end sub

sub onTabSelected()
    selectedIndex = m.tabList.itemSelected
    selectedTab = m.tabList.content.getChild(selectedIndex)
    
    if selectedTab <> invalid
        m.currentContentType = selectedTab.contentType
        loadCatalog(m.currentContentType)
    end if
end sub

sub loadCatalog(contentType as String)
    showLoading(true)
    
    m.task = CreateObject("roSGNode", "FetchTask")
    m.task.requestUrl = m.backendIp + "/api/famelack/catalog?content_type=" + contentType
    m.task.observeField("responseJson", "onCatalogLoaded")
    m.task.control = "RUN"
end sub

sub onCatalogLoaded()
    showLoading(false)
    
    catalog = m.task.responseJson
    
    if catalog = invalid or catalog.categories = invalid or catalog.categories.Count() = 0
        print("Error loading catalog")
        m.loadingLabel.text = "No content available. Check server."
        m.loadingLabel.visible = true
        return
    end if
    
    content = CreateObject("roSGNode", "ContentNode")
    
    for each cat in catalog.categories
        for each item in cat.items
            node = content.CreateChild("ContentNode")
            node.title = item.title
            if item.hdPosterUrl <> invalid and item.hdPosterUrl <> "" and Instr(1, item.hdPosterUrl, "via.placeholder.com") = 0
                node.HDPosterUrl = item.hdPosterUrl
            else
                node.HDPosterUrl = "pkg:/images/Famelack.png"
            end if
            node.addField("targetUrl", "string", false)
            node.targetUrl = item.targetUrl
            node.addField("description", "string", false)
            node.description = item.description
        end for
    end for
    
    m.mediaGrid.content = content
    m.mediaGrid.visible = true
    m.mediaGrid.setFocus(true)
end sub

sub onItemSelected()
    selectedItem = m.mediaGrid.content.getChild(m.mediaGrid.itemSelected)
    
    if selectedItem <> invalid
        loadStream(selectedItem.targetUrl)
    end if
end sub

sub loadStream(url as String)
    showLoading(true)
    
    m.streamTask = CreateObject("roSGNode", "FetchTask")
    m.streamTask.requestUrl = m.backendIp + "/api/famelack/stream?url=" + url
    m.streamTask.observeField("responseJson", "onStreamLoaded")
    m.streamTask.control = "RUN"
end sub

sub onStreamLoaded()
    showLoading(false)
    
    streamData = m.streamTask.responseJson
    
    if streamData = invalid or streamData.streamUrl = invalid
        print("Error loading stream")
        return
    end if
    
    videoContent = CreateObject("roSGNode", "ContentNode")
    videoContent.url = streamData.streamUrl
    videoContent.streamFormat = streamData.streamFormat
    videoContent.title = streamData.title
    
    m.videoPlayer.content = videoContent
    m.videoPlayer.visible = true
    m.videoPlayer.setFocus(true)
    m.videoPlayer.control = "play"
    
    ' Hide media grid when video is playing
    m.mediaGrid.visible = false
end sub

sub onVideoState()
    state = m.videoPlayer.state
    
    if state = "finished" or state = "stopped"
        ' Return to grid when video ends
        m.videoPlayer.visible = false
        m.mediaGrid.visible = true
        m.mediaGrid.setFocus(true)
    end if
end sub

sub showLoading(show as Boolean)
    m.loadingLabel.visible = show
    if show
        m.loadingLabel.setFocus(true)
    end if
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    
    if key = "back"
        if m.videoPlayer.visible
            ' Exit video player
            m.videoPlayer.control = "stop"
            m.videoPlayer.visible = false
            m.mediaGrid.visible = true
            m.mediaGrid.setFocus(true)
            return true
        end if
    end if
    
    return false
end function
