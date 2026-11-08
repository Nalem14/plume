// The window of Notes: the view (NotesView.qml), its size kept. Opened by Meta+N alone, it stays hidden behind
// the quick note; closed while the quick note is open, it only hides.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    width: app.windowSize.width
    height: app.windowSize.height
    minimumWidth: 760
    minimumHeight: 500
    visible: !startQuick
    title: app.t.app_name
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: close => {
        view.flush()
        app.saveWindow(width, height)
        if (view.quickNoteOpen) {
            close.accepted = false
            window.hide()
        }
    }

    NotesView {
        id: view
        objectName: "view"
        anchors.fill: parent
        onRaiseWanted: {
            if (!window.visible) window.show()
            if (window.visibility === Window.Minimized) window.showNormal()
            window.raise()
            window.requestActivate()
        }
        onQuickClosed: if (!window.visible) Qt.quit()
    }
}
