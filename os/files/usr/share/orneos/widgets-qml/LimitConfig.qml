// The widgets whose only setting is how many items they show (Meet, Fichiers récents, Deck).
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S

Kirigami.FormLayout {
    id: root
    property int cfg_limit: 8
    QQC2.SpinBox {
        Kirigami.FormData.label: S.tr("itemCount")
        from: 1; to: 20
        value: root.cfg_limit
        onValueModified: root.cfg_limit = value
    }
}
