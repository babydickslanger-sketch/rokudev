sub Init()
    m.backButton = m.top.findNode("backButton")
    m.seriesTitle = m.top.findNode("seriesTitle")
    m.seasonList = m.top.findNode("seasonList")
    m.episodeGrid = m.top.findNode("episodeGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    m.loadingLabel = m.top.findNode("loadingLabel")
    
    ' Set backend IP - update this to match your server
    m.backendIp = "http://192.168.1.46:8000"
    
    ' Series data
    m.seriesData = invalid
    m.currentSeason = 0
    
    ' Observe events
    m.seasonList.observeField("itemSelected", "onSeasonSelected")
    m.episodeGrid.observeField("itemSelected", "onEpisodeSelected")
    m.videoPlayer.observeField("state", "onVideoState")
    
    ' Load series data
    loadSeriesData()
end sub

sub loadSeriesData()
    showLoading(true)
    
    ' Get content ID from scene parameters
    contentId = m.top.contentId
    
    if contentId = invalid or contentId = ""
        print("No content ID provided")
        return
    end if
    
    m.task = CreateObject("roSGNode", "FetchTask")
    m.task.requestUrl = m.backendIp + "/api/moviebox/detail/" + contentId
    m.task.observeField("responseJson", "onSeriesDataLoaded")
    m.task.control = "RUN"
end sub

sub onSeriesDataLoaded()
    showLoading(false)
    
    m.seriesData = m.task.responseJson
    
    if m.seriesData = invalid
        print("Error loading series data")
        return
    end if
    
    ' Set title
    m.seriesTitle.text = m.seriesData.title
    
    ' Setup seasons
    setupSeasons()
    
    ' Load first season
    if m.seriesData.seasons <> invalid and m.seriesData.seasons.Count() > 0
        loadSeason(0)
    end if
end sub

sub setupSeasons()
    content = CreateObject("roSGNode", "ContentNode")
    
    if m.seriesData.seasons <> invalid
        for each season in m.seriesData.seasons
            node = content.CreateChild("ContentNode")
            node.title = "Season " + stri(season.seasonNumber)
            node.addField("seasonNumber", "integer", false)
            node.seasonNumber = season.seasonNumber
        end for
    end if
    
    m.seasonList.content = content
    m.seasonList.setFocus(true)
end sub

sub onSeasonSelected()
    selectedIndex = m.seasonList.itemSelected
    selectedSeason = m.seasonList.content.getChild(selectedIndex)
    
    if selectedSeason <> invalid
        loadSeason(selectedIndex)
    end if
end sub

sub loadSeason(seasonIndex as Integer)
    m.currentSeason = seasonIndex
    
    if m.seriesData.seasons = invalid or seasonIndex >= m.seriesData.seasons.Count()
        return
    end if
    
    season = m.seriesData.seasons[seasonIndex]
    
    content = CreateObject("roSGNode", "ContentNode")
    
    if season.episodes <> invalid
        for each episode in season.episodes
            node = content.CreateChild("ContentNode")
            node.title = episode.title
            node.HDPosterUrl = "https://via.placeholder.com/300x200.png"
            node.addField("streamUrl", "string", false)
            node.streamUrl = episode.streamUrl
            node.addField("episodeNumber", "integer", false)
            node.episodeNumber = episode.episodeNumber
        end for
    end if
    
    m.episodeGrid.content = content
    m.episodeGrid.visible = true
    m.episodeGrid.setFocus(true)
end sub

sub onEpisodeSelected()
    selectedIndex = m.episodeGrid.itemSelected
    selectedEpisode = m.episodeGrid.content.getChild(selectedIndex)
    
    if selectedEpisode <> invalid
        playEpisode(selectedEpisode.streamUrl)
    end if
end sub

sub playEpisode(streamUrl as String)
    showLoading(true)
    
    m.streamTask = CreateObject("roSGNode", "FetchTask")
    m.streamTask.requestUrl = m.backendIp + "/api/moviebox/stream?url=" + streamUrl
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
    
    ' Hide episode grid when video is playing
    m.episodeGrid.visible = false
end sub

sub onVideoState()
    state = m.videoPlayer.state
    
    if state = "finished" or state = "stopped"
        ' Return to episode grid when video ends
        m.videoPlayer.visible = false
        m.episodeGrid.visible = true
        m.episodeGrid.setFocus(true)
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
            m.episodeGrid.visible = true
            m.episodeGrid.setFocus(true)
            return true
        else
            ' Exit detail scene
            m.top.close = true
            return true
        end if
    end if
    
    return false
end function
