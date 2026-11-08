import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S
Kirigami.FormLayout {
    id: root
    required property string kind
    property string cfg_folder: ""
    property int cfg_limit: 8
    QQC2.TextField {
        visible: root.kind === "team"
        Kirigami.FormData.label: S.tr("teamFolder")
        text: root.cfg_folder
        onTextEdited: root.cfg_folder = text
        placeholderText: S.tr("folderExample")
    }
    QQC2.Label { visible: root.kind === "team"; text: S.tr("folderHelp"); wrapMode: Text.WordWrap; LayoutMirroring.enabled: false }
    QQC2.SpinBox { Kirigami.FormData.label: S.tr("itemCount"); from: 1; to: 20; value: root.cfg_limit; onValueModified: root.cfg_limit = value }
}
