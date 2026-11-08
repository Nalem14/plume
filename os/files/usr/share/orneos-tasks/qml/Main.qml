// The window of Tâches: the view (TasksView.qml), its size kept. Closing it keeps the reminders (the app
// stays in the session).
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
    title: app.t.app_name
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: close => {
        app.saveWindow(width, height)
        close.accepted = false
        window.hide()
    }

    TasksView {
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
    }
}
