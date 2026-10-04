sub Init()
    m.top.functionName = "executeRequest"
end sub

sub executeRequest()
    urlTransfer = CreateObject("roUrlTransfer")
    urlTransfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    urlTransfer.InitClientCertificates()
    requestUrl = m.top.requestUrl
    if m.top.queryValue <> invalid and m.top.queryValue <> ""
        requestUrl = requestUrl + urlTransfer.Escape(m.top.queryValue)
    end if
    urlTransfer.SetUrl(requestUrl)
    urlTransfer.AddHeader("Content-Type", "application/json")
    
    port = CreateObject("roMessagePort")
    urlTransfer.SetMessagePort(port)
    
    timeoutSeconds = m.top.requestTimeoutSeconds
    if timeoutSeconds = invalid or timeoutSeconds <= 0
        timeoutSeconds = 10
    end if

    if urlTransfer.AsyncGetToString()
        msg = wait(timeoutSeconds * 1000, port)
        if type(msg) = "roUrlEvent"
            statusCode = msg.GetResponseCode()
            responseText = msg.GetString()
            m.top.statusCode = statusCode
            m.top.responseText = responseText
            print "Streaming Hub FetchTask HTTP status: " + stri(statusCode) + "; timeoutSeconds=" + stri(timeoutSeconds)
            if statusCode = 200
                if responseText <> invalid and responseText <> ""
                    parsed = ParseJson(responseText)
                    if parsed <> invalid
                        m.top.responseJson = parsed
                        return
                    end if
                end if
                m.top.errorMessage = "HTTP 200 response was not valid JSON"
                print "Streaming Hub FetchTask JSON parse failed"
            else
                m.top.errorMessage = msg.GetFailureReason()
                print "Streaming Hub FetchTask HTTP failure: " + m.top.errorMessage
            end if
        else
            m.top.errorMessage = "Timed out waiting for HTTP response"
            print "Streaming Hub FetchTask timed out: " + requestUrl
        end if
    else
        m.top.errorMessage = "AsyncGetToString failed to start"
        print "Streaming Hub FetchTask request did not start: " + requestUrl
    end if

    m.top.responseJson = {}
end sub
