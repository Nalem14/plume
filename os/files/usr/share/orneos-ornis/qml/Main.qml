// The window of Ornis: the view (OrnisView.qml), its size kept, the conversation in its title.
// Closing it keeps the app in the session (Code cron tasks still fire); the dock or a second launch brings it back.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    width: app.windowSize.width
    height: app.windowSize.height
    minimumWidth: 640
    minimumHeight: 460
    visible: true
    title: chat.current ? chat.title + " — Ornis" : "Ornis"
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: close => {
        app.saveWindow(width, height)
        close.accepted = false
        window.hide()
    }

    OrnisView {
        id: view
        objectName: "view"
        anchors.fill: parent
        onRaiseWanted: {
            if (!window.visible) window.show()
            if (window.visibility === Window.Minimized) window.showNormal()
            window.raise()
            window.requestActivate()
        }
    }
}
