// People Recognize took for different persons: the ones ticked join this one (or the named one among them).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string ref
    readonly property var person: (photos.lists.people || []).find(p => p.id === ref) || ({})
    width: Math.min(560, parent ? parent.width - 48 : 560)
    tint: theme.c.famMedia
    title: app.t.person_merge_title.replace("%1", person.name || app.t.person_unnamed)

    property string filter: ""
    property var picked: []
    function toggle(id) {
        const next = picked.slice(), at = next.indexOf(id)
        if (at >= 0) next.splice(at, 1); else next.push(id)
        picked = next
    }
    // the others, named first (the most seen first, as in the list), narrowed by the name typed
    readonly property var others: {
        const f = filter.trim().toLowerCase()
        return (photos.lists.people || []).filter(p => p.id !== ref
                                                  && (!f || (p.name || "").toLowerCase().indexOf(f) >= 0))
    }

    function openFor(id) { ref = id; filter = ""; picked = []; search.text = ""; open(); search.forceActiveFocus() }

    Text {
        Layout.fillWidth: true
        text: app.t.person_merge_pick
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    OTextField {
        id: search
        Layout.fillWidth: true
        visible: (photos.lists.people || []).length > 8
        placeholderText: app.t.person_merge_search
        onTextChanged: dialog.filter = text
    }
    // 150 faces do not fit: they scroll, the buttons stay in sight
    ScrollView {
        id: scroller
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(faces.implicitHeight, Math.max(160, (dialog.parent ? dialog.parent.height : 700) - 300))
        contentWidth: availableWidth
        clip: true
        GridLayout {
            id: faces
            width: scroller.availableWidth
            columns: 4
            rowSpacing: 12; columnSpacing: 12
            Repeater {
                model: dialog.others
                AbstractButton {
                    id: face
                    required property var modelData
                    Layout.preferredWidth: (scroller.availableWidth - 36) / 4
                    Layout.maximumWidth: (scroller.availableWidth - 36) / 4
                    implicitHeight: 120
                    hoverEnabled: true
                    checkable: true
                    checked: dialog.picked.indexOf(modelData.id) >= 0
                    Accessible.name: modelData.name || app.t.person_unnamed
                    Accessible.role: Accessible.CheckBox
                    onClicked: dialog.toggle(modelData.id)
                    background: Rectangle {
                        radius: 10
                        color: face.checked ? Qt.alpha(theme.c.action, 0.10) : face.hovered ? theme.c.hover : "transparent"
                        border.width: face.checked ? 2 : 0; border.color: theme.c.action
                    }
                    contentItem: ColumnLayout {
                        spacing: 6
                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            implicitWidth: 76; implicitHeight: 76; radius: 38; clip: true
                            color: theme.c.line
                            Thumb {
                                anchors.fill: parent
                                address: "c/recognize/" + face.modelData.cover + "/" + face.modelData.etag + "/"
                                        + encodeURIComponent((app.profile.user || "") + "/" + face.modelData.id)
                                sourceSize: Qt.size(160, 160)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                            }
                            Corners { anchors.fill: parent; radius: width / 2; color: face.hovered ? theme.c.hover : theme.c.overlay }
                            Rectangle {
                                visible: face.checked
                                anchors.right: parent.right; anchors.bottom: parent.bottom
                                width: 24; height: 24; radius: 12
                                color: theme.c.action; border.width: 2; border.color: theme.c.overlay
                                Icon { anchors.centerIn: parent; name: "check"; size: 13; color: theme.c.actionText }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: (face.modelData.name || app.t.person_unnamed) + "\n" + app.plural("count_photos", face.modelData.count)
                            elide: Text.ElideRight
                            maximumLineCount: 2
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: !face.modelData.name
                            color: theme.c.text
                        }
                    }
                }
            }
        }
    }
    Text {
        visible: dialog.others.length === 0
        Layout.fillWidth: true
        text: app.t.person_merge_none
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"
            enabled: dialog.picked.length > 0
            text: dialog.picked.length ? app.t.person_merge_many.replace("%1", dialog.picked.length) : app.t.person_merge_action
            onClicked: { photos.mergePeople(dialog.ref, dialog.picked); dialog.close() }
        }
    ]
}
