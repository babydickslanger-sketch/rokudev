sub Init()
    m.categoryList = m.top.findNode("categoryList")
    m.mediaGrid = m.top.findNode("mediaGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    
    ' Get backend IP from interface
    m.backendIp = m.top.backendIp
    
    ' Default backend IP if not provided
    if m.backendIp = invalid or m.backendIp = ""
        m.backendIp = "http://192.168.1.46:8000"
    end if
    
    ' Current category
    m.currentCategory = ""
    
    ' Setup categories
    setupCategories()
    
    ' Observe events
    m.categoryList.observeField("itemSelected", "onCategorySelected")
    m.mediaGrid.observeField("itemSelected", "onItemSelected")
    m.videoPlayer.observeField("state", "onVideoState")
    
    ' Load initial catalog
    loadCatalog("")
end sub

sub setupCategories()
    content = CreateObject("roSGNode", "ContentNode")
    
    categories = [
        {title: "Popular Series", slug: "popular-series"},
        {title: "Popular Movie", slug: "popular-movie"},
        {title: "Anime", slug: "anime"},
        {title: "Action Movies", slug: "action-movies"},
        {title: "Romance", slug: "romance"},
        {title: "Horror Movies", slug: "horror-movies"},
        {title: "K-Drama", slug: "k-drama"},
        {title: "Sitcom", slug: "sitcom"}
    ]
    
    for each cat in categories
        node = content.CreateChild("ContentNode")
        node.title = cat.title
        node.addField("slug", "string", false)
        node.slug = cat.slug
    end for
    
    m.categoryList.content = content
    m.categoryList.setFocus(true)
end sub

sub onCategorySelected()
    selectedIndex = m.categoryList.itemSelected
    selectedCategory = m.categoryList.content.getChild(selectedIndex)
    
    if selectedCategory <> invalid
        m.currentCategory = selectedCategory.slug
        loadCatalog(m.currentCategory)
    end if
end sub

sub loadCatalog(categorySlug as String)
    showLoading(true)
    
    url = m.backendIp + "/api/moviebox/catalog"
    if categorySlug <> ""
        url = url + "?category=" + categorySlug
    end if
    
    m.task = CreateObject("roSGNode", "FetchTask")
    m.task.requestUrl = url
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
    
    ' Use local MovieBox images instead of placeholders
    imageIndex = 1
    
    for each cat in catalog.categories
        for each item in cat.items
            node = content.CreateChild("ContentNode")
            node.title = item.title
                if item.hdPosterUrl <> invalid and item.hdPosterUrl <> "" and Instr(1, item.hdPosterUrl, "via.placeholder.com") = 0
                    node.HDPosterUrl = item.hdPosterUrl
                else
                    node.HDPosterUrl = "pkg:/images/MovieBox.png"
                end if
            node.addField("contentId", "string", false)
            node.contentId = item.id
            node.addField("contentType", "string", false)
            node.contentType = item.contentType
            node.addField("detailUrl", "string", false)
            node.detailUrl = item.detailUrl
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
        if selectedItem.contentType = "series"
            ' Load detail view for TV series
            loadSeriesDetail(selectedItem.contentId)
        else
            ' Load stream directly for movies
            loadStream(selectedItem.detailUrl)
        end if
    end if
end sub

sub loadSeriesDetail(contentId as String)
    showLoading(true)
    
    m.detailTask = CreateObject("roSGNode", "FetchTask")
    m.detailTask.requestUrl = m.backendIp + "/api/moviebox/detail/" + contentId
    m.detailTask.observeField("responseJson", "onSeriesDetailLoaded")
    m.detailTask.control = "RUN"
end sub

sub onSeriesDetailLoaded()
    showLoading(false)
    
    detail = m.detailTask.responseJson
    
    if detail = invalid
        print("Error loading series detail")
        return
    end if

    if detail.seasons <> invalid and detail.seasons.Count() > 0
        firstSeason = detail.seasons[0]
        if firstSeason.episodes <> invalid and firstSeason.episodes.Count() > 0
            firstEpisode = firstSeason.episodes[0]
            loadStream(firstEpisode.streamUrl)
        end if
    else if detail.streamUrl <> invalid
        loadStream(detail.streamUrl)
    end if
end sub

sub loadStream(url as String)
    showLoading(true)
    
    m.streamTask = CreateObject("roSGNode", "FetchTask")
    m.streamTask.requestUrl = m.backendIp + "/api/moviebox/stream?url=" + url
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
    
    ' Add Widevine DRM support
    videoContent.addField("drmType", "string", false)
    videoContent.drmType = "widevine"
    
    ' Add DRM configuration if provided by backend
    if streamData.drmConfig <> invalid
        videoContent.addField("drmConfig", "assocarray", false)
        videoContent.drmConfig = streamData.drmConfig
    else
        ' Default DRM configuration for Widevine
        drmConfig = {
            "keySystem": "com.widevine.alpha",
            "licenseServer": streamData.licenseUrl
        }
        videoContent.addField("drmConfig", "assocarray", false)
        videoContent.drmConfig = drmConfig
    end if
    
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
        else
            ' Return to main menu
            m.top.sceneClosed = true
            return true
        end if
    end if
    
    return false
end function
