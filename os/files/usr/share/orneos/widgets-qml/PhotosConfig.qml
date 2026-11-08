// Photos, display: recent, favourites, on this day or one album of the cloud; how often the photo changes.
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S

Kirigami.FormLayout {
    id: root
    property string cfg_source: "recent"
    property int cfg_seconds: 30
    readonly property var choices: [{id: "recent", name: S.tr("recentPhotos")}, {id: "favorites", name: S.tr("favoritePhotos")},
                                    {id: "onthisday", name: S.tr("onThisDay")}]
        .concat((bridge.result.albums || []).map(a => ({id: "album:" + a.id, name: S.tr("album") + " · " + a.name})))
    readonly property var periods: [10, 30, 60, 300, 900]
    Bridge { id: bridge; command: "/usr/libexec/orneos-widget photos --source=recent"; interval: 600000 }
    QQC2.ComboBox {
        Kirigami.FormData.label: S.tr("show")
        model: root.choices
        textRole: "name"
        currentIndex: Math.max(0, root.choices.findIndex(c => c.id === root.cfg_source))
        onActivated: root.cfg_source = root.choices[currentIndex].id
    }
    QQC2.ComboBox {
        Kirigami.FormData.label: S.tr("changeEvery")
        model: root.periods.map(n => n < 60 ? S.fmt("everySeconds", n) : S.fmt("everyMinutes", n / 60))
        currentIndex: Math.max(0, root.periods.indexOf(root.cfg_seconds))
        onActivated: root.cfg_seconds = root.periods[currentIndex]
    }
}
