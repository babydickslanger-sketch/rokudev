sub Init()
    m.top.functionName = "executeRequest"
end sub

sub executeRequest()
    transfer = CreateObject("roUrlTransfer")
    transfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    transfer.InitClientCertificates()
    requestUrl = m.top.requestUrl
    if m.top.queryValue <> invalid and m.top.queryValue <> ""
        requestUrl = requestUrl + transfer.Escape(m.top.queryValue)
    end if
    print "FBStream FetchTask GET: " + requestUrl
    transfer.SetUrl(requestUrl)

    port = CreateObject("roMessagePort")
    transfer.SetMessagePort(port)

    timeoutSeconds = m.top.requestTimeoutSeconds
    if timeoutSeconds = invalid or timeoutSeconds <= 0
        timeoutSeconds = 10
    end if

    if transfer.AsyncGetToString()
        message = wait(timeoutSeconds * 1000, port)
        if type(message) = "roUrlEvent"
            statusCode = message.GetResponseCode()
            responseText = message.GetString()
            m.top.statusCode = statusCode
            m.top.responseText = responseText
            print "FBStream FetchTask HTTP status: " + stri(statusCode) + "; timeoutSeconds=" + stri(timeoutSeconds)
            print "FBStream FetchTask response length: " + stri(Len(responseText))
            print "FBStream FetchTask response (first 500 chars): " + Left(responseText, 500)
            if statusCode = 200
                parsed = ParseJson(responseText)
                if parsed <> invalid
                    m.top.responseJson = parsed
                    print "FBStream FetchTask JSON parse successful"
                    return
                end if
                m.top.errorMessage = "HTTP 200 response was not valid JSON"
                print "FBStream FetchTask JSON parse failed - response was not valid JSON"
                print "FBStream FetchTask raw response: " + responseText
            else
                m.top.errorMessage = message.GetFailureReason()
                print "FBStream FetchTask HTTP failure: " + m.top.errorMessage
                print "FBStream FetchTask failure reason: " + message.GetFailureReason()
            end if
        else
            m.top.errorMessage = "Timed out waiting for HTTP response"
            print "FBStream FetchTask timed out after " + stri(timeoutSeconds) + " seconds: " + requestUrl
        end if
    else
        m.top.errorMessage = "AsyncGetToString failed to start"
        print "FBStream FetchTask request did not start: " + requestUrl
    end if

    m.top.responseJson = {}
end sub