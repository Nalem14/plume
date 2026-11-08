import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S

Kirigami.FormLayout {
    id: root
    required property string kind
    property string cfg_view: "recent"
    property string cfg_group: ""
    property int cfg_limit: 8
    readonly property bool mail: kind === "mail"
    readonly property var groups: [{id: "", name: S.tr(mail ? "allBoxes" : "allFolders")}].concat(bridge.result.groups || [])
    Bridge { id: bridge; command: "/usr/libexec/orneos-widget " + root.kind; interval: 30000 }
    QQC2.ComboBox {
        Kirigami.FormData.label: S.tr("view")
        model: [S.tr(root.mail ? "recentMail" : "recent"), S.tr(root.mail ? "unread" : "pinned")]
        currentIndex: root.cfg_view === "recent" ? 0 : 1
        onActivated: root.cfg_view = currentIndex === 0 ? "recent" : root.mail ? "unread" : "pinned"
    }
    QQC2.ComboBox {
        Kirigami.FormData.label: S.tr(root.mail ? "mailbox" : "folder")
        model: root.groups
        textRole: "name"
        currentIndex: root.groups.findIndex(g => g.id === root.cfg_group)
        onActivated: root.cfg_group = root.groups[currentIndex].id
    }
    QQC2.SpinBox {
        Kirigami.FormData.label: S.tr("itemCount")
        from: 1; to: 20
        value: root.cfg_limit
        onValueModified: root.cfg_limit = value
    }
    QQC2.Label {
        visible: !bridge.result.ready
        text: S.tr(bridge.result.state || "loading")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
}
