// The window of Photos: the view (PhotosView.qml), its size kept.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    width: app.windowSize.width
    height: app.windowSize.height
    minimumWidth: 800
    minimumHeight: 540
    visible: true
    title: app.t.app_name
    color: theme.c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: {
        app.saveWindow(width, height)
        if (!photos.leave()) Qt.quit()
    }

    PhotosView {
        id: view
        objectName: "view"
        anchors.fill: parent
        onRaiseWanted: {
            if (!window.visible) {          // closed, its last changes still going up: it comes back
                photos.stay()
                window.show()
            }
            if (window.visibility === Window.Minimized) window.showNormal()
            window.raise()
            window.requestActivate()
        }
        onFullScreenWanted: on => window.visibility = on ? Window.FullScreen : Window.Windowed
    }
}
