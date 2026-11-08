// The window of Meet: the view (MeetView.qml), its size kept. Closing it keeps the app in the session (calls
// ring, messages notify); a call goes on behind, the dock's pin brings it back.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    width: app.windowSize.width
    height: app.windowSize.height
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: calls.active ? calls.name + " · " + app.t.app_name : app.t.app_name
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: close => {
        app.saveWindow(width, height)
        close.accepted = false
        window.hide()
    }

    MeetView {
        id: view
        objectName: "view"
        anchors.fill: parent
        onRaiseWanted: {
            if (!window.visible) window.show()
            if (window.visibility === Window.Minimized) window.showNormal()
            window.raise()
            window.requestActivate()
        }
        onCloseWanted: window.close()
        onFullScreenWanted: on => window.visibility = on ? Window.FullScreen : Window.Windowed
    }
}
