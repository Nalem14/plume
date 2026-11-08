// GIFs of Giphy, searched through the cloud (its Giphy integration: Giphy never sees this computer); the
// trending ones before a search. A GIF leaves as its Giphy link, like Talk web sends it (its card there).
// show(item, term); picked(link).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

MeetMenu {
    id: picker
    implicitWidth: 380
    property var results: []
    property bool searching: false
    signal picked(string url)

    function show(item, term) {
        query.text = term
        popupAbove(item)
        search()
    }
    function search() {
        searching = true
        meet.searchGifs(query.text)
    }
    onOpened: query.forceActiveFocus()
    Connections {
        target: meet
        function onGifsFound(term, found) {
            if (term !== query.text.trim()) return
            picker.searching = false
            picker.results = found
        }
    }
    Timer { id: typing; interval: 450; onTriggered: picker.search() }

    ColumnLayout {
        width: picker.implicitWidth - 12
        spacing: 8
        OTextField {
            id: query
            Layout.fillWidth: true
            iconName: "search"
            placeholderText: app.t.gif_search
            onTextChanged: if (picker.opened) typing.restart()
            Keys.onReturnPressed: { typing.stop(); picker.search() }
        }
        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.preferredHeight: 300
            clip: true
            cellWidth: Math.floor(width / 3); cellHeight: 96
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            model: picker.results
            delegate: AbstractButton {
                id: cell
                required property var modelData
                width: grid.cellWidth; height: grid.cellHeight
                hoverEnabled: true
                Accessible.name: modelData.title
                ToolTip.visible: hovered && modelData.title !== ""
                ToolTip.delay: 700
                ToolTip.text: modelData.title
                onClicked: { picker.picked(modelData.url); picker.close() }
                property string file: meet.gif(modelData.id, true)
                Connections {
                    target: meet
                    enabled: cell.file === ""
                    function onGifReady(id) { if (id === cell.modelData.id) cell.file = meet.gif(cell.modelData.id, true) }
                }
                background: Rectangle { radius: 8; color: theme.c.hover; border.width: cell.hovered ? 2 : 0; border.color: theme.c.action }
                contentItem: AnimatedImage {
                    source: cell.file
                    fillMode: Image.PreserveAspectCrop
                    playing: picker.opened
                    clip: true
                }
                padding: 3
            }
            Text {
                anchors.centerIn: parent
                visible: grid.count === 0
                text: picker.searching ? app.t.gif_loading : app.t.gif_none
                font.pixelSize: 13; color: theme.c.muted
            }
        }
        Text {
            Layout.alignment: Qt.AlignRight
            text: app.t.gif_powered
            font.pixelSize: 10; color: theme.c.faint
        }
    }
}
