sub Init()
    m.categoryList = m.top.findNode("categoryList")
    m.mediaGrid = m.top.findNode("mediaGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    m.backendIp = "http://192.168.1.46:8000"

    setupCategories()
    m.categoryList.observeField("itemSelected", "onCategorySelected")
    m.mediaGrid.observeField("itemSelected", "onItemSelected")
    m.videoPlayer.observeField("state", "onVideoState")
    loadCatalog("live-now")
    print "FBStream Init complete - auto-loading live-now"
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
    m.task.requestTimeoutSeconds = 10
    print "FBStream loading category: " + category
    m.task.observeField("responseJson", "onCatalogLoaded")
    m.task.control = "RUN"
end sub

sub onCatalogLoaded()
    showLoading(false)
    catalog = m.task.responseJson
    print "FBStream onCatalogLoaded - statusCode=" + stri(m.task.statusCode)
    print "FBStream onCatalogLoaded - errorMessage=" + m.task.errorMessage
    if catalog <> invalid
        print "FBStream onCatalogLoaded - responseJson valid=true"
    else
        print "FBStream onCatalogLoaded - responseJson valid=false"
    end if
    if catalog = invalid
        print "FBStream catalog is invalid - JSON parse failed or network error"
        showEmptyState("Error: " + m.task.errorMessage + " (HTTP " + stri(m.task.statusCode) + ")")
        return
    end if
    categories = catalog["categories"]
    if categories = invalid
        print "FBStream catalog.categories is invalid - response structure mismatch"
        keys = catalog.Keys()
        print "FBStream catalog keys count=" + stri(keys.Count())
        showEmptyState("Error: Invalid response structure from backend")
        return
    end if
    if categories.Count() = 0
        print "FBStream catalog.categories.Count() = 0 - no categories returned"
        showEmptyState("No categories available from backend")
        return
    end if

    content = CreateObject("roSGNode", "ContentNode")
    eventCount = 0
    for each category in categories
        categoryCount = 0
        items = category["items"]
        if items <> invalid
            for each event in items
                categoryCount = categoryCount + 1
                eventCount = eventCount + 1
                node = content.CreateChild("ContentNode")
                node.title = event["title"]
                node.shortDescriptionLine1 = event["title"]
                node.shortDescriptionLine2 = event["description"]
                posterUrl = event["hdPosterUrl"]
                if posterUrl <> invalid and posterUrl <> ""
                    node.HDPosterUrl = posterUrl
                else
                    node.HDPosterUrl = "pkg:/images/FBStream.png"
                end if
                node.addField("targetUrl", "string", false)
                node.targetUrl = event["targetUrl"]
            end for
        end if
        print "FBStream category '" + category["title"] + "' events=" + stri(categoryCount)
    end for

    nodeCount = content.getChildCount()
    print "FBStream catalog mapped events=" + stri(eventCount) + "; grid nodes=" + stri(nodeCount)
    if nodeCount = 0
        showEmptyState("The response contained no event items")
        return
    end if
    m.categoryList.visible = false
    m.mediaGrid.content = content
    m.mediaGrid.visible = true
    m.mediaGrid.setFocus(true)
    if m.mediaGrid.visible
        print "FBStream event grid visible=true"
    else
        print "FBStream event grid visible=false"
    end if
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
    print "FBStream resolving event with timeoutSeconds=240 url=" + url
    m.streamTask.observeField("responseJson", "onStreamLoaded")
    m.streamTask.control = "RUN"
end sub

sub onStreamLoaded()
    showLoading(false)
    streamData = m.streamTask.responseJson
    if streamData = invalid or streamData.streamUrl = invalid
        print "FBStream stream resolution failed; HTTP status=" + stri(m.streamTask.statusCode) + "; error=" + m.streamTask.errorMessage
        print "FBStream stream response: " + m.streamTask.responseText
        showPlaybackError()
        return
    end if
    playbackUrl = streamData.streamUrl
    if streamData.playbackUrl <> invalid and streamData.playbackUrl <> ""
        playbackUrl = streamData.playbackUrl
    end if
    if streamData.directStreamUrl <> invalid and streamData.directStreamUrl <> ""
        print "FBStream direct stream URL available but using proxy for SSL compatibility"
    end if
    if streamData.extractor <> invalid then print "FBStream extractor=" + streamData.extractor
    if streamData.playbackId <> invalid then print "FBStream playbackId=" + streamData.playbackId
    if streamData.streamFormat <> invalid then print "FBStream streamFormat=" + streamData.streamFormat
    print "FBStream playback URL: " + playbackUrl
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
    print "FBStream video state=" + m.videoPlayer.state
    if m.videoPlayer.state = "error"
        print "FBStream video playback error for URL"
        showPlaybackError()
    end if
    if m.videoPlayer.state = "finished" or m.videoPlayer.state = "stopped" or m.videoPlayer.state = "error"
        m.videoPlayer.visible = false
        m.mediaGrid.visible = true
        m.mediaGrid.setFocus(true)
    end if
    if m.videoPlayer.state = "buffering"
        print "FBStream video is buffering - starting 90-second startup timeout"
        m.bufferingTimer = m.top.createChild("Timer")
        m.bufferingTimer.duration = 90
        m.bufferingTimer.observeField("fire", "onBufferingTimeout")
        m.bufferingTimer.control = "start"
    end if
end sub

sub onBufferingTimeout()
    print "FBStream buffering timeout after 90 seconds - stream may be incompatible"
    print "FBStream video errorCode=" + stri(m.videoPlayer.errorCode) + "; errorMsg=" + m.videoPlayer.errorMsg
    if m.videoPlayer.state = "buffering"
        m.videoPlayer.control = "stop"
        showPlaybackError()
    end if
    if m.bufferingTimer <> invalid
        m.bufferingTimer.control = "stop"
    end if
end sub

sub showEmptyState(reason as String)
    print "FBStream empty state: " + reason
    m.categoryList.visible = true
    m.categoryList.setFocus(true)
    m.mediaGrid.visible = false
    m.loadingLabel.text = reason
    m.loadingLabel.visible = true
end sub

sub showPlaybackError()
    m.loadingLabel.text = "Unable to play this event. Try another event."
    m.loadingLabel.visible = true
end sub

sub showLoading(show as Boolean)
    m.loadingLabel.text = "Loading..."
    m.loadingLabel.visible = show
    if show
        m.categoryList.visible = false
        m.mediaGrid.visible = false
    end if
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
            m.top.close = true
        end if
        return true
    end if
    return false
end function