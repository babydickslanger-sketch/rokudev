sub Init()
    m.categoryList = m.top.findNode("categoryList")
    m.mediaGrid = m.top.findNode("mediaGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    m.backendIp = m.top.backendIp
    if m.backendIp = invalid or m.backendIp = ""
        m.backendIp = "http://192.168.1.46:8000"
    end if
    setupCategories()
    m.categoryList.observeField("itemSelected", "onCategorySelected")
    m.mediaGrid.observeField("itemSelected", "onItemSelected")
    m.videoPlayer.observeField("state", "onVideoState")
    loadCatalog("live-now")
end sub

sub setupCategories()
    content = CreateObject("roSGNode", "ContentNode")
    categories = [
        {title: "Live Now", slug: "live-now"},
        {title: "Football", slug: "football"},
        {title: "NFL", slug: "nfl"},
        {title: "Basketball", slug: "basketball"},
        {title: "NBA", slug: "nba"},
        {title: "Hockey", slug: "hockey"},
        {title: "NHL", slug: "nhl"},
        {title: "Baseball", slug: "baseball"},
        {title: "MLB", slug: "mlb"},
        {title: "Tennis", slug: "tennis"},
        {title: "Motorsports", slug: "motorsports"},
        {title: "F1", slug: "f1"},
        {title: "MotoGP", slug: "motogp"},
        {title: "UFC", slug: "ufc"},
        {title: "MMA", slug: "mma"},
        {title: "Boxing", slug: "boxing"}
    ]
    for each category in categories
        node = content.CreateChild("ContentNode")
        node.title = category.title
        node.addField("slug", "string", false)
        node.slug = category.slug
    end for
    m.categoryList.content = content
    m.categoryList.setFocus(true)
end sub

sub onCategorySelected()
    category = m.categoryList.content.getChild(m.categoryList.itemSelected)
    if category <> invalid
        loadCatalog(category.slug)
    end if
end sub

sub loadCatalog(category as String)
    showLoading(true)
    m.task = CreateObject("roSGNode", "FetchTask")
    m.task.requestUrl = m.backendIp + "/api/fbstream/catalog?category=" + category
    m.task.observeField("responseJson", "onCatalogLoaded")
    m.task.control = "RUN"
end sub

sub onCatalogLoaded()
    showLoading(false)
    catalog = m.task.responseJson
    if catalog = invalid or catalog.categories = invalid or catalog.categories.Count() = 0
        showEmptyState()
        return
    end if

    content = CreateObject("roSGNode", "ContentNode")
    for each category in catalog.categories
        for each event in category.items
            node = content.CreateChild("ContentNode")
            node.title = event.title
            if event.hdPosterUrl <> invalid and event.hdPosterUrl <> ""
                node.HDPosterUrl = event.hdPosterUrl
            else
                node.HDPosterUrl = "pkg:/images/FBStream.png"
            end if
            node.addField("targetUrl", "string", false)
            node.targetUrl = event.targetUrl
        end for
    end for

    if content.getChildCount() = 0
        showEmptyState()
        return
    end if
    m.mediaGrid.content = content
    m.mediaGrid.visible = true
    m.mediaGrid.setFocus(true)
end sub

sub onItemSelected()
    event = m.mediaGrid.content.getChild(m.mediaGrid.itemSelected)
    if event <> invalid
        loadStream(event.targetUrl)
    end if
end sub

sub loadStream(url as String)
    showLoading(true)
    m.streamTask = CreateObject("roSGNode", "FetchTask")
    m.streamTask.requestUrl = m.backendIp + "/api/fbstream/stream?url="
    m.streamTask.queryValue = url
    m.streamTask.requestTimeoutSeconds = 240
    print "FBStream hub resolving event with timeoutSeconds=240 url=" + url
    m.streamTask.observeField("responseJson", "onStreamLoaded")
    m.streamTask.control = "RUN"
end sub

sub onStreamLoaded()
    showLoading(false)
    streamData = m.streamTask.responseJson
    if streamData = invalid or streamData.streamUrl = invalid
        print "FBStream hub stream resolution failed; HTTP status=" + stri(m.streamTask.statusCode) + "; error=" + m.streamTask.errorMessage
        print "FBStream hub stream response: " + m.streamTask.responseText
        showEmptyState()
        return
    end if
    playbackUrl = streamData.streamUrl
    if streamData.playbackUrl <> invalid and streamData.playbackUrl <> ""
        playbackUrl = streamData.playbackUrl
    end if
    if streamData.extractor <> invalid then print "FBStream hub extractor=" + streamData.extractor
    if streamData.playbackId <> invalid then print "FBStream hub playbackId=" + streamData.playbackId
    if streamData.streamFormat <> invalid then print "FBStream hub streamFormat=" + streamData.streamFormat
    print "FBStream hub playback URL: " + playbackUrl
    content = CreateObject("roSGNode", "ContentNode")
    content.url = playbackUrl
    content.streamFormat = streamData.streamFormat
    content.title = streamData.title
    m.videoPlayer.content = content
    m.videoPlayer.visible = true
    m.mediaGrid.visible = false
    m.videoPlayer.setFocus(true)
    m.videoPlayer.control = "play"
end sub

sub onVideoState()
    print "FBStream hub video state=" + m.videoPlayer.state
    if m.videoPlayer.state = "finished" or m.videoPlayer.state = "stopped" or m.videoPlayer.state = "error"
        m.videoPlayer.visible = false
        m.mediaGrid.visible = true
        m.mediaGrid.setFocus(true)
    end if
end sub

sub showEmptyState()
    m.loadingLabel.text = "No events available. Check the backend."
    m.loadingLabel.visible = true
end sub

sub showLoading(show as Boolean)
    m.loadingLabel.text = "Loading..."
    m.loadingLabel.visible = show
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false
    if key = "back"
        if m.videoPlayer.visible
            m.videoPlayer.control = "stop"
            m.videoPlayer.visible = false
            m.mediaGrid.visible = true
            m.mediaGrid.setFocus(true)
        else
            m.top.sceneClosed = true
        end if
        return true
    end if
    return false
end function