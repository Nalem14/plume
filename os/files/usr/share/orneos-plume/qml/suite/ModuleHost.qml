// Where Notes, Tâches, Mots de passe, Ornis, Meet or the Photothèque sit in Plume: their own view (suite.mount), made the first time the module shows.
// While the app is open in its own window, the module only offers to bring that window up.
import QtQuick
import QtQuick.Window
import "../components"

Item {
    id: host
    property string kind
    property var view: null
    property bool wasMaximized: false
    readonly property bool elsewhere: suite.elsewhere.indexOf(kind) >= 0

    function ensure() {
        if (view || elsewhere || !visible)
            return
        view = suite.mount(kind, host)
        if (!view)
            return
        view.anchors.fill = host
        if (view.viewKeys !== undefined)
            view.viewKeys = false              // Ctrl+1… switch modules in Plume
        if (view.fullScreenWanted !== undefined)   // the Photothèque's viewer (F, the slideshow): the whole window
            view.fullScreenWanted.connect(on => {
                const w = host.Window.window
                if (!w) return
                if (on) { host.wasMaximized = w.visibility === Window.Maximized; w.showFullScreen() }
                else if (host.wasMaximized) w.showMaximized()
                else w.showNormal()
            })
    }
    onVisibleChanged: ensure()
    onElsewhereChanged: ensure()
    Component.onCompleted: ensure()

    EmptyState {
        anchors.fill: parent
        visible: host.elsewhere
        iconName: ({ notes: "note", tasks: "checklist", passwords: "key", meet: "video", photos: "image" })[host.kind] || "ornis"
        title: plume.t.elsewhere_title.replace("%1", plume.t[host.kind])
        lead: plume.t.elsewhere_lead.replace("%1", plume.t[host.kind])
        actionText: plume.t.elsewhere_action
        actionIcon: "openExternal"
        onActivated: suite.openElsewhere(host.kind)
    }
}
