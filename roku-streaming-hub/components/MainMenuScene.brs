sub Init()
    m.menuGroup = m.top.findNode("menuGroup")
    m.appGrid = m.top.findNode("appGrid")
    m.viewContainer = m.top.findNode("viewContainer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    m.activeView = invalid
    
    ' Set backend IP
    m.backendIp = "http://192.168.1.46:8000"
    
    ' Setup app selection grid
    setupAppGrid()
    
    ' Observe selection
    m.appGrid.observeField("itemSelected", "onAppSelected")
    
    m.appGrid.setFocus(true)
end sub

sub setupAppGrid()
    content = CreateObject("roSGNode", "ContentNode")
    
    ' Famelack App
    famelackNode = content.CreateChild("ContentNode")
    famelackNode.title = "Famelack"
        famelackNode.HDPosterUrl = "pkg:/images/Famelack.png"
    famelackNode.addField("appType", "string", false)
    famelackNode.appType = "famelack"
    famelackNode.description = "Live TV, Radio & Webcams"
    
    ' MovieBox App
    movieboxNode = content.CreateChild("ContentNode")
    movieboxNode.title = "MovieBox"
        movieboxNode.HDPosterUrl = "pkg:/images/MovieBox.png"
    movieboxNode.addField("appType", "string", false)
    movieboxNode.appType = "moviebox"
    movieboxNode.description = "Movies & TV Series"

    ' FBStream App
    fbstreamNode = content.CreateChild("ContentNode")
    fbstreamNode.title = "FBStream"
        fbstreamNode.HDPosterUrl = "pkg:/images/FBStream.png"
    fbstreamNode.addField("appType", "string", false)
    fbstreamNode.appType = "fbstream"
    fbstreamNode.description = "Live Sports"
    
    m.appGrid.content = content
end sub

sub onAppSelected()
    selectedIndex = m.appGrid.itemSelected
    selectedApp = m.appGrid.content.getChild(selectedIndex)
    
    if selectedApp <> invalid
        if selectedApp.appType = "famelack"
            launchFamelack()
        else if selectedApp.appType = "moviebox"
            launchMovieBox()
        else if selectedApp.appType = "fbstream"
            launchFBStream()
        end if
    end if
end sub

sub launchFamelack()
    m.menuGroup.visible = false
    
    m.activeView = m.viewContainer.createChild("FamelackScene")
    m.activeView.backendIp = m.backendIp
    m.activeView.observeField("sceneClosed", "onViewClosed")
    m.activeView.setFocus(true)
end sub

sub launchMovieBox()
    m.menuGroup.visible = false
    
    m.activeView = m.viewContainer.createChild("MovieBoxScene")
    m.activeView.backendIp = m.backendIp
    m.activeView.observeField("sceneClosed", "onViewClosed")
    m.activeView.setFocus(true)
end sub

sub launchFBStream()
    m.menuGroup.visible = false

    m.activeView = m.viewContainer.createChild("FBStreamScene")
    m.activeView.backendIp = m.backendIp
    m.activeView.observeField("sceneClosed", "onViewClosed")
    m.activeView.setFocus(true)
end sub

sub onViewClosed()
    if m.activeView <> invalid
        m.viewContainer.removeChild(m.activeView)
        m.activeView = invalid
    end if
    m.menuGroup.visible = true
    m.appGrid.setFocus(true)
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    
    if key = "back"
        if m.activeView <> invalid
            onViewClosed()
            return true
        else
            m.top.close = true
            return true
        end if
    end if
    
    return false
end function
