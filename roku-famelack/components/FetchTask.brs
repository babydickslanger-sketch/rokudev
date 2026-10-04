sub Init()
    m.top.functionName = "executeRequest"
end sub

sub executeRequest()
    urlTransfer = CreateObject("roUrlTransfer")
    urlTransfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    urlTransfer.InitClientCertificates()
    urlTransfer.SetUrl(m.top.requestUrl)
    urlTransfer.AddHeader("Content-Type", "application/json")
    
    port = CreateObject("roMessagePort")
    urlTransfer.SetMessagePort(port)
    
    if urlTransfer.AsyncGetToString()
        msg = wait(10000, port)
        if type(msg) = "roUrlEvent"
            statusCode = msg.GetResponseCode()
            if statusCode = 200
                jsonString = msg.GetString()
                if jsonString <> invalid and jsonString <> ""
                    parsed = ParseJson(jsonString)
                    if parsed <> invalid
                        m.top.responseJson = parsed
                        return
                    end if
                end if
            else
                print "HTTP Error status code: " + stri(statusCode) + " failure: " + msg.GetFailureReason()
            end if
        else
            print "FetchTask timeout waiting for response from: " + m.top.requestUrl
        end if
    else
        ' Fallback to synchronous request
        jsonString = urlTransfer.GetToString()
        if jsonString <> invalid and jsonString <> ""
            parsed = ParseJson(jsonString)
            if parsed <> invalid
                m.top.responseJson = parsed
                return
            end if
        end if
    end if
    
    ' Fallback notification on error
    m.top.responseJson = {}
end sub
