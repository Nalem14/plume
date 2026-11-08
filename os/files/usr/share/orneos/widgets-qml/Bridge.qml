import QtQuick
import org.kde.plasma.plasma5support as Plasma5Support

Item {
    id: root
    property string command: ""
    property int interval: 60000
    property var result: ({ready: false, state: "loading"})
    property bool busy: false
    property bool actionBusy: false
    signal actionFinished(bool ok)
    function quote(value) { return "'" + String(value).replace(/'/g, "'\\''") + "'"; }
    function refresh() {
        if (command && !actionBusy) {
            busy = true;
            source.connectSource(command);
        }
    }
    function launch(command) { actions.connectSource("setsid -f " + command + " >/dev/null 2>&1"); }
    function run(command) {
        source.disconnectSource(root.command);
        actionBusy = true;
        actions.connectSource(command);
    }
    onCommandChanged: { result = {ready: false, state: "loading"}; refresh(); }
    Component.onCompleted: refresh()
    Timer { interval: root.interval; running: !!root.command; repeat: true; onTriggered: root.refresh() }
    Plasma5Support.DataSource {
        id: source
        engine: "executable"
        connectedSources: []
        onNewData: (name, data) => {
            disconnectSource(name);
            if (name !== root.command || root.actionBusy) return;
            root.busy = false;
            try { root.result = JSON.parse(data.stdout); }
            catch (e) { root.result = {ready: false, state: "error"}; }
        }
    }
    Plasma5Support.DataSource {
        id: actions
        engine: "executable"
        connectedSources: []
        onNewData: (name, data) => {
            disconnectSource(name);
            let ok = data["exit code"] === 0;
            if (name.indexOf("/usr/libexec/orneos-widget complete") === 0) {
                try {
                    const snapshot = JSON.parse(data.stdout);
                    ok = snapshot.ready === true;
                    if (ok) root.result = snapshot;
                }
                catch (e) { ok = false; }
            }
            // Every action frees the bridge (not only completing a task), or the widget would stop refreshing.
            root.actionBusy = false;
            root.actionFinished(ok);
            root.refresh();
        }
    }
}
