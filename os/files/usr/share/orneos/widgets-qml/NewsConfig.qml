// Actualités, display: which source (all, starred, a folder or a feed of the cloud's News), unread only, count.
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S

Kirigami.FormLayout {
    id: root
    property string cfg_source: "all"
    property bool cfg_unreadOnly: false
    property int cfg_limit: 8
    readonly property var choices: [{id: "all", name: S.tr("allSources")}, {id: "starred", name: S.tr("starred")}]
        .concat((bridge.result.folders || []).map(f => ({id: "folder:" + f.id, name: S.fmt("folderPrefix", f.name)})))
        .concat((bridge.result.feeds || []).map(f => ({id: "feed:" + f.id, name: f.name})))
    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget news --lang=" + quote(Qt.locale().name.slice(0, 2))
        interval: 30000
    }
    QQC2.ComboBox {
        Kirigami.FormData.label: S.tr("source")
        model: root.choices
        textRole: "name"
        currentIndex: Math.max(0, root.choices.findIndex(c => c.id === root.cfg_source))
        onActivated: root.cfg_source = root.choices[currentIndex].id
    }
    QQC2.CheckBox {
        text: S.tr("unreadOnly")
        checked: root.cfg_unreadOnly
        onToggled: root.cfg_unreadOnly = checked
    }
    QQC2.SpinBox {
        Kirigami.FormData.label: S.tr("itemCount")
        from: 1; to: 20
        value: root.cfg_limit
        onValueModified: root.cfg_limit = value
    }
}
