// Photos: the sidebar (the library, favourites, videos, memories, people, places, the albums), the head of the
// view and its photos, laid out at their own proportions. A photo opens in the viewer; Modifier opens the editor.
// Signed out or loading for the first time, it shows only that state.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool ready: app.connected && photos.state === "ready"
    readonly property bool shown: ready && visible && !viewer.opened && !editor.opened
    readonly property var head: photos.heading
    // years, months, memories, people, places, albums and the trash are cards; the rest, rows of photos
    readonly property bool gridView: ["people", "places", "memories", "albums", "trash"].indexOf(photos.view) < 0
                                     && !(photos.view === "library" && photos.mode !== "all")
    // the places on the map rather than as cities
    // a search on its way: the cloud's filters, or Ornis still reading the sentence
    readonly property bool searching: photos.view === "search" && (photos.search.busy || (ornis.busy && photos.search.ornis === false
                                                                                           && photos.rows.length === 0))
    readonly property bool onMap: photos.view === "places" && app.prefs.places_mode === "map"
    property bool mapSeen: false
    onOnMapChanged: if (onMap) mapSeen = true
    // the photos chosen (Ctrl+clic, Maj+clic, Ctrl+A), by file id; in the trash, by path
    property var chosen: []
    property int anchorIndex: -1
    property alias toast: toast
    property bool viewKeys: true         // Ctrl+1, 2, 3: years, months, all; in Plume they switch modules
    signal raiseWanted()
    signal fullScreenWanted(bool on)

    function bringUp() { raiseWanted() }
    function isChosen(id) { return chosen.indexOf(id) >= 0 }
    function clearChoice() { chosen = []; anchorIndex = -1 }
    // a click on a photo: alone it opens; with Ctrl, or while photos are chosen, it joins or leaves the choice
    function clickPhoto(fileid, index, forceChoose) {
        const mod = app.modifier()
        if (mod === "shift" && anchorIndex >= 0) {
            const range = photos.between(anchorIndex, index)
            const next = chosen.slice()
            for (const id of range) if (next.indexOf(id) < 0) next.push(id)
            chosen = next
            return
        }
        if (mod === "ctrl" || forceChoose || chosen.length > 0) {
            const next = chosen.slice()
            const at = next.indexOf(fileid)
            if (at >= 0) next.splice(at, 1); else next.push(fileid)
            chosen = next
            anchorIndex = index
            return
        }
        viewer.open(fileid)
    }
    function targets(fileid) { return isChosen(fileid) || fileid === undefined ? chosen.slice() : [fileid] }
    function remove(ids) {
        if (!ids.length) return
        photos.delete(ids)
        chosen = chosen.filter(id => ids.indexOf(id) < 0)
    }
    function addToAlbum(ids, item) {
        albumMenu.openFor(ids, item)
    }
    function runSearch(text) {
        const q = text.trim()
        if (!q) { if (photos.view === "search") photos.setView("library"); return }
        const quick = photos.quickMatch(q)
        if (quick) { photos.setView(quick); return }
        if (/^(19|20)\d\d$/.test(q)) {
            photos.runSearch({ query: q, from: q + "-01-01", to: q + "-12-31" })
            return
        }
        photos.runSearch({ query: q })
        ornis.search(q)
    }
    function openView(v) { clearChoice(); photos.setView(v) }
    // Ctrl+wheel, Ctrl+ / Ctrl−, a pinch: in the library, years → months → every photo then its three sizes
    // (as Photos on macOS); elsewhere, the three sizes
    function zoomBy(d) {
        if (photos.view !== "library") { photos.setZoom(photos.zoom + d); return }
        const modes = ["years", "months"]
        const at = photos.mode === "all" ? 2 + photos.zoom : modes.indexOf(photos.mode)
        const next = Math.max(0, Math.min(4, at + d))
        if (next === at) return
        if (next < 2) { photos.setMode(modes[next]); return }
        photos.setZoom(next - 2)
        if (photos.mode !== "all") photos.setMode("all")
    }

    onVisibleChanged: if (visible) grid.relayout()

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onRaiseRequested() { win.bringUp() }
        function onShowRequested(fileid) {
            if (!photos.photo(fileid).fileid) { app.openCloud("/f/" + fileid); return }
            viewer.open(fileid); win.bringUp()
        }
        function onActionRequested(action, value) {
            if (action === "import") photos.importFiles(JSON.parse(value))
            else if (action === "view") win.openView(value)
            else if (action === "search") { sidebar.setSearch(value); win.runSearch(value) }
            win.bringUp()
        }
    }
    Connections {
        target: photos
        function onViewChanged() {
            if (win.chosen.length && photos.view !== "trash")
                win.chosen = win.chosen.filter(id => photos.order.indexOf(id) >= 0)
        }
        function onDone(what, ok, message) {
            if (!ok) problem.tell(message)
            else if (what === "deleted") toast.show(message, app.t.undo, () => photos.undoDelete(), 6)
            else if (what === "download" && message.indexOf("/") >= 0) toast.show(message, app.t.open_folder, () => photos.openDownloads(), 6)
            else if (message) toast.show(message)
        }
    }
    Connections {
        target: ornis
        function onPlanned(sentence, plan) { if (photos.view === "search" && photos.search.query === sentence) photos.runSearch(plan) }
        function onTitled(titles) { photos.setMemoryTitles(titles) }
        function onFailed(kind, message) { toast.show(message) }
    }

    Shortcut { sequence: "Ctrl+F"; enabled: win.shown; onActivated: sidebar.focusSearch() }
    Shortcut { sequence: "Ctrl+A"; enabled: win.shown && photos.order.length > 0; onActivated: win.chosen = photos.order.slice() }
    Shortcut { sequence: "Escape"; enabled: win.shown && win.chosen.length > 0; onActivated: win.clearChoice() }
    Shortcut { sequences: ["Delete", "Backspace"]; enabled: win.shown && win.chosen.length > 0 && photos.view !== "trash"; onActivated: win.remove(win.chosen.slice()) }
    Shortcut { sequence: "."; enabled: win.shown && win.chosen.length > 0; onActivated: photos.toggleFavorite(win.chosen) }
    Shortcut { sequence: "Ctrl+I"; enabled: win.shown; onActivated: importDialog.open() }
    Shortcut { sequence: "Ctrl+,"; enabled: win.shown; onActivated: settings.open() }
    Shortcut { sequences: ["Ctrl++", "Ctrl+="]; enabled: win.shown && (grid.visible || photos.view === "library"); onActivated: win.zoomBy(1) }
    Shortcut { sequence: "Ctrl+-"; enabled: win.shown && (grid.visible || photos.view === "library"); onActivated: win.zoomBy(-1) }
    Shortcut { sequence: "Ctrl+1"; enabled: win.shown && win.viewKeys; onActivated: { win.openView("library"); photos.setMode("years") } }
    Shortcut { sequence: "Ctrl+2"; enabled: win.shown && win.viewKeys; onActivated: { win.openView("library"); photos.setMode("months") } }
    Shortcut { sequence: "Ctrl+3"; enabled: win.shown && win.viewKeys; onActivated: { win.openView("library"); photos.setMode("all") } }
    Shortcut { sequence: "F5"; enabled: win.shown; onActivated: photos.refresh() }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: win.ready

        Band { Layout.fillHeight: true; color: win.c.famMedia }
        Sidebar {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: win.width >= 1180 ? 272 : 244
            onSettingsRequested: settings.open()
            onImportRequested: importDialog.open()
            onNewAlbum: nameDialog.ask("album-new", "", "", [])
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: win.c.bg

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                anchors.bottomMargin: 0
                spacing: 12

                ViewHead {
                    id: viewHead
                    Layout.fillWidth: true
                    onShareAlbum: shareDialog.openFor(photos.heading.ref)
                    onRenameAlbum: nameDialog.ask("album-rename", photos.heading.ref, photos.heading.title, [])
                    onDeleteAlbum: albumDelete.ask(app.t.album_delete_title.replace("%1", photos.heading.title), app.t.album_delete_text,
                                                   [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.album_delete, kind: "danger" }],
                                                   () => photos.deleteAlbum(photos.heading.ref))
                    onRenamePerson: nameDialog.ask("person", photos.heading.ref, photos.heading.named ? photos.heading.title : "", [])
                    onMergePerson: mergeDialog.openFor(photos.heading.ref)
                    onImportRequested: importDialog.open()
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // the photos lie on a sheet raised from the page, like the lists of Tâches
                    Surface {
                        anchors.fill: parent
                        anchors.bottomMargin: 18
                        radius: 14
                        visible: grid.visible
                    }
                    PhotoGrid {
                        id: grid
                        anchors.fill: parent
                        anchors.margins: 14; anchors.topMargin: 6; anchors.bottomMargin: 26
                        visible: win.gridView && photos.rows.length > 0
                        bottomMargin: win.chosen.length > 0 ? 72 : 0      // the last row clears the bar
                        onAlbumWanted: (ids, item) => win.addToAlbum(ids, item)
                        onEditWanted: fileid => editor.open(fileid)
                    }
                    CardGrid {
                        id: cards
                        anchors.fill: parent
                        visible: !win.gridView && !win.onMap
                        onYearPicked: card => { photos.setMode("months"); cards.showMonthOf(card.year) }
                        onMonthPicked: card => { photos.setMode("all"); grid.showDay(card.dayid) }
                    }
                    // made the first time it is shown, kept after (where it was left, its tiles)
                    Loader {
                        id: map
                        anchors.fill: parent
                        anchors.bottomMargin: 18
                        active: win.onMap || win.mapSeen
                        visible: win.onMap
                        source: "MapPane.qml"
                    }
                    // over the photos, at the bottom: the grid never moves under the pointer when a choice starts
                    SelectionBar {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 34
                        width: Math.min(parent.width - 40, 760)
                        z: 6
                        visible: win.chosen.length > 0
                        onAlbumWanted: item => win.addToAlbum(win.chosen.slice(), item)
                    }
                    Skeleton {
                        anchors.fill: parent; anchors.topMargin: 6
                        visible: photos.loadingView || win.searching
                        tone: win.c.line; lead: false; rows: 6
                        Accessible.name: app.t.loading
                    }
                    EmptyState {
                        anchors.fill: parent
                        visible: win.gridView && photos.rows.length === 0 && !photos.loadingView && !win.searching
                        iconName: photos.view === "search" ? "search" : photos.view === "favorites" ? "star"
                                : photos.view === "archive" ? "archive"
                                : photos.view === "videos" ? "video" : photos.view === "library" ? "image" : "album"
                        title: photos.view === "search" ? app.t.empty_search_title
                             : photos.view === "archive" ? app.t.empty_archive_title
                             : photos.view === "favorites" ? app.t.empty_favorites_title
                             : photos.view === "videos" ? app.t.empty_videos_title
                             : photos.view === "library" ? app.t.empty_library_title : app.t.empty_album_title
                        lead: photos.view === "search" ? app.t.empty_search_lead
                            : photos.view === "archive" ? app.t.empty_archive_lead
                            : photos.view === "favorites" ? app.t.empty_favorites_lead
                            : photos.view === "videos" ? app.t.empty_videos_lead
                            : photos.view === "library" ? app.t.empty_library_lead.replace("%1", (photos.folders[0] || "/Photos"))
                            : app.t.empty_album_lead
                        actionText: photos.view === "library" ? app.t.import_action : ""
                        actionIcon: "import"
                        onActivated: importDialog.open()
                    }
                }
            }
        }
    }

    // files from Dolphin or the desktop dropped on the window go into the library
    DropArea {
        id: fileDrop
        anchors.fill: parent
        enabled: win.ready && !editor.opened
        keys: ["text/uri-list"]
        onDropped: drop => {
            if (drop.hasUrls && drop.formats.indexOf("application/x-orneos-photos") < 0) {
                photos.importFiles(drop.urls.map(u => u.toString()))
                drop.accept(Qt.CopyAction)
            }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 10
            visible: fileDrop.containsDrag && fileDrop.drag.formats.indexOf("application/x-orneos-photos") < 0
            radius: 14
            color: Qt.alpha(win.c.famMedia, 0.10)
            border.width: 2; border.color: win.c.famMedia
            Column {
                anchors.centerIn: parent
                spacing: 10
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "import"; size: 34; color: win.c.famMedia }
                Text {
                    text: app.t.drop_import.replace("%1", photos.folders[0] || "/Photos")
                    font.family: "Schibsted Grotesk"; font.pixelSize: 17; font.weight: Font.DemiBold
                    color: win.c.text
                }
            }
        }
    }

    EmptyState {
        anchors.fill: parent
        visible: !app.connected
        iconName: "image"
        title: app.t.welcome_title
        lead: app.t.welcome_lead
        actionText: app.t.welcome_action
        onActivated: app.openConnect()
    }
    Rectangle {
        anchors.fill: parent
        visible: app.connected && photos.state !== "ready"
        color: win.c.bg
        Skeleton { anchors.fill: parent; anchors.margins: 28; visible: photos.state === "loading"; tone: win.c.line; lead: false; rows: 8; Accessible.name: app.t.loading }
        EmptyState {
            anchors.fill: parent
            visible: photos.state === "offline_first" || photos.state === "error_first"
            iconName: photos.state === "offline_first" ? "offline" : "warning"
            title: photos.state === "offline_first" ? app.t.first_offline_title : app.t.first_error_title
            lead: photos.state === "offline_first" ? app.t.first_offline_lead : app.t.first_error_lead
            actionText: app.t.retry
            actionIcon: "refresh"
            onActivated: photos.refresh()
        }
    }

    Viewer {
        id: viewer
        anchors.fill: parent
        onEditWanted: fileid => editor.open(fileid)
        onAlbumWanted: (ids, item) => win.addToAlbum(ids, item)
        onFullScreenWanted: on => win.fullScreenWanted(on)
    }
    Editor {
        id: editor
        anchors.fill: parent
        onSaved: (fileid, shownId) => { if (viewer.opened) viewer.show(shownId) }
    }

    AlbumMenu { id: albumMenu; onNewAlbum: ids => nameDialog.ask("album-new", "", "", ids) }
    DateDialog { id: dateDialog }
    // « Partager avec… »: the photos go into a new album (named for today), then its people are chosen
    QtObject {
        id: shareAlbum
        function ask(ids) {
            if (!ids.length) return
            const today = new Date().toLocaleDateString(Qt.locale(), Locale.LongFormat).replace(/^\w+,?\s*/, "")
            nameDialog.ask("share", "", app.t.share_album_name.replace("%1", today), ids)
        }
    }
    Connections {
        target: photos
        function onShareReady(album) { shareDialog.openFor(album) }
    }
    NameDialog { id: nameDialog }
    MergeDialog { id: mergeDialog }
    ShareDialog { id: shareDialog }
    SettingsDialog { id: settings }
    ImportDialog { id: importDialog }
    ChoiceDialog { id: albumDelete }
    ProblemDialog { id: problem }
    Toast { id: toast; z: 20 }
}
