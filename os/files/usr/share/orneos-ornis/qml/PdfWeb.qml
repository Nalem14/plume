// A PDF of this computer shown in the file panel (FilePane), by Chromium's own PDF viewer: pages, zoom, search,
// print. A profile that keeps nothing; nothing but the file itself is loaded (its links go to the browser). Loaded on
// demand: without QtWebEngine (or its PDF viewer), the panel keeps its card « Ouvrir avec l'application ».
import QtQuick
import QtWebEngine

WebEngineView {
    id: web
    property string file: ""            // file:// of the PDF
    url: file
    backgroundColor: theme.c.field
    profile: WebEngineProfile {
        offTheRecord: true
        httpCacheType: WebEngineProfile.MemoryHttpCache
        persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies
    }
    settings.pluginsEnabled: true                        // Chromium's PDF viewer
    settings.pdfViewerEnabled: true
    settings.localContentCanAccessFileUrls: false
    settings.localContentCanAccessRemoteUrls: false
    settings.javascriptCanOpenWindows: false
    settings.javascriptCanAccessClipboard: false
    settings.localStorageEnabled: false
    settings.screenCaptureEnabled: false
    onNavigationRequested: request => {
        const url = request.url.toString()
        if (!request.isMainFrame || url.split("#")[0] === web.file || url === "about:blank") return
        request.reject()
        if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) app.openLink(url)
    }
    onNewWindowRequested: request => app.openLink(request.requestedUrl.toString())
    onPermissionRequested: permission => permission.deny()
    onFileDialogRequested: request => { request.accepted = true; request.dialogReject() }
}
