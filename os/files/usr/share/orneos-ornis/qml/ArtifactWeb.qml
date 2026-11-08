// An artifact of an answer (a page, a drawing, a diagram) drawn by Chromium, in its own sandbox: a profile that
// keeps nothing, no access to the computer's files (the page is a private file of its own), its links opened in
// the browser, no new windows, no permissions (camera, location…). Loaded on demand by PreviewPane: without
// QtWebEngine, the pane keeps its text rendering.
import QtQuick
import QtWebEngine

WebEngineView {
    id: web
    property string page: ""            // file:// of the artifact's page (app.artifactUrl)
    url: page
    backgroundColor: theme.c.bg
    profile: WebEngineProfile {
        offTheRecord: true
        httpCacheType: WebEngineProfile.MemoryHttpCache
        persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies
    }
    settings.localContentCanAccessFileUrls: false
    settings.localContentCanAccessRemoteUrls: true       // a page may use a library from a CDN, as on the web
    settings.javascriptCanOpenWindows: false
    settings.javascriptCanAccessClipboard: false
    settings.localStorageEnabled: false
    settings.pluginsEnabled: false
    settings.screenCaptureEnabled: false
    settings.webGLEnabled: true
    onNavigationRequested: request => {
        const url = request.url.toString()
        if (url.split("#")[0] === web.page || url.startsWith("data:") || url === "about:blank")
            return                                         // the page itself, an anchor of it
        if (request.isMainFrame) {                         // a link of the page: in the browser, never here
            request.reject()
            if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) app.openLink(request.url.toString())
        }
    }
    onNewWindowRequested: request => app.openLink(request.requestedUrl.toString())
    onPermissionRequested: permission => permission.deny()
    onFileDialogRequested: request => { request.accepted = true; request.dialogReject() }
}
