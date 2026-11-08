// The window of Mots de passe: the view (PasswordsView.qml), its size kept.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    width: app.windowSize.width
    height: app.windowSize.height
    minimumWidth: 820
    minimumHeight: 540
    visible: true
    title: app.t.app_name
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: {
        app.saveWindow(width, height)
        app.windowClosed()
    }

    PasswordsView {
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
