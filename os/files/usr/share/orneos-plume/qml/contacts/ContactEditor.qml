// New or edited contact: photo, name, company, as many addresses and numbers as needed (their kind, or a label
// of one's own), birthday, anniversary, nickname, related people, groups, notes.
// A card of a read-only book (an Orneos account, someone written to) is edited into my contacts.
// Every item keeps what it came with (_head, _kind, _value, _label…: vcard.py writes it back as it was).
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"

ODialog {
    id: editor
    property var info: ({})
    property var emails: []
    property var phones: []
    property var addresses: []
    property var related: []
    property var groups: []
    property var photo: null             // null: the card's photo stays; "": removed; data: URL: the new one
    readonly property string shownPhoto: photo !== null ? photo : (info.photoView || "")
    property var taken: ({})             // email row → the other card that has this address
    signal saved(int contactId)
    signal openOther(int contactId)

    width: Math.min(660, parent ? parent.width - 48 : 660)
    title: info.contactId ? plume.t.edit_contact : plume.t.new_contact
    // typing must not be lost to a click beside the window: only Escape and « Annuler » close it
    closePolicy: Popup.CloseOnEscape

    function kindsFor(list) {
        const base = list === "emails" ? ["home", "work", "other"]
                   : list === "phones" ? ["cell", "work", "home", "fax", "other"]
                   : ["home", "work", "other"]
        return base.map(v => ({ text: plume.t["type_" + v], value: v }))
    }
    readonly property var relations: ["spouse", "child", "parent", "sibling", "friend", "colleague", "assistant", "other"]
        .map(v => ({ text: plume.t["rel_" + v], value: v }))

    function copyItems(list) { return (list || []).map(x => Object.assign({}, x)) }

    function openNew(prefill) {
        info = { contactId: 0, bookId: people.defaultBook }
        given.text = ""; family.text = ""; org.text = ""; job.text = ""; bday.text = ""; notes.text = ""; website.text = ""
        nickname.text = ""; anniv.text = ""
        photo = null; bdayError.visible = false; annivError.visible = false; taken = ({})
        emails = [{ type: "home", value: prefill && prefill.email ? prefill.email : "" }]
        phones = [{ type: "cell", value: "" }]
        addresses = []
        related = []
        groups = people.group ? [people.group] : []
        // a name typed in the capture line: the first word is the given name, the rest the family name
        if (prefill && prefill.name) {
            const words = prefill.name.trim().split(/\s+/)
            given.text = words[0]
            family.text = words.slice(1).join(" ")
        }
        open()
        given.forceActiveFocus()
        if (prefill && prefill.email) checkTaken(0, prefill.email)
    }

    // extra: fields to add before showing (what Ornis read in a signature); nothing is saved before « Enregistrer »
    function openEdit(card, extra) {
        info = card
        given.text = card.given; family.text = card.family
        // a card without N (a company, a phone's quick entry): its shown name, split like a typed one
        if (!card.given && !card.family && card.fn && card.fn !== card.org && card.emails.every(e => e.value !== card.fn)) {
            const words = card.fn.trim().split(/\s+/)
            given.text = words[0]
            family.text = words.slice(1).join(" ")
        }
        org.text = card.org; job.text = card.title; bday.text = people.birthdayText(card.bday); notes.text = card.note; website.text = card.url
        nickname.text = card.nickname || ""; anniv.text = people.birthdayText(card.anniversary || "")
        photo = null; bdayError.visible = false; annivError.visible = false; taken = ({})
        emails = card.emails.length ? copyItems(card.emails) : [{ type: "home", value: "" }]
        phones = card.phones.length ? copyItems(card.phones) : [{ type: "cell", value: "" }]
        addresses = copyItems(card.addresses)
        related = copyItems(card.related)
        groups = card.categories.slice()
        if (extra) {
            if (extra.org && !org.text) org.text = extra.org
            if (extra.title && !job.text) job.text = extra.title
            if (extra.url && !website.text) website.text = extra.url
            const digits = v => v.replace(/\D/g, "").slice(-9)
            const known = phones.filter(p => p.value).map(p => digits(p.value))
            const added = (extra.phones || []).filter(p => known.indexOf(digits(p.value)) < 0)
            phones = phones.filter(p => p.value.trim()).concat(added)
            if (!phones.length) phones = [{ type: "cell", value: "" }]
            if (extra.address && !addresses.length)
                addresses = [Object.assign({ type: "work", region: "" }, extra.address)]
        }
        open()
        given.forceActiveFocus()
    }

    function checkTaken(index, value) {
        const owner = people.emailOwner(value, info.contactId || 0)
        const t = Object.assign({}, taken)
        if (owner.id) t[index] = owner; else delete t[index]
        taken = t
    }

    function save() {
        const birthday = people.birthday(bday.text)
        if (birthday === "?") {
            bdayError.visible = true
            bday.forceActiveFocus()
            return
        }
        const anniversary = people.birthday(anniv.text)
        if (anniversary === "?") {
            annivError.visible = true
            anniv.forceActiveFocus()
            return
        }
        const filled = [given.text, family.text, org.text, job.text, nickname.text].some(t => t.trim())
                       || emails.some(e => e.value.trim()) || phones.some(p => p.value.trim())
        if (!filled) {
            given.forceActiveFocus()
            return
        }
        const fields = {
            contactId: info.contactId || 0, bookId: book.currentValue || people.defaultBook,
            given: given.text.trim(), family: family.text.trim(), org: org.text.trim(), title: job.text.trim(),
            fn: [given.text.trim(), family.text.trim()].filter(x => x).join(" "), nickname: nickname.text.trim(),
            emails: emails.filter(e => e.value.trim()), phones: phones.filter(p => p.value.trim()),
            addresses: addresses.filter(a => (a.street + a.city + a.code + (a.region || "") + a.country).trim()),
            related: related.filter(r => r.value.trim()),
            bday: birthday, anniversary: anniversary, note: notes.text.trim(), url: website.text.trim(), categories: groups,
            photo: photo
        }
        const id = people.save(fields)
        close()
        saved(id)
    }

    // In place, the list not reassigned: that rebuilt every row, the drop-down or field being clicked included,
    // and the click then landed on the field below
    function setAt(list, index, key, value) {
        editor[list][index][key] = value
    }

    component Label_: Text {
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: theme.c.muted
    }

    // the kind of one item (Pro, Perso, Mobile…), or a label of one's own (« Maison de vacances », from a phone too)
    component KindBox: OComboBox {
        id: kindBox
        property string list
        property int index
        property var item: ({})
        Layout.preferredWidth: 132
        model: editor.kindsFor(list).concat(item.label ? [{ text: item.label, value: "label" }] : [])
                                     .concat([{ text: plume.t.type_custom, value: "custom" }])
        Component.onCompleted: select(item.label ? "label" : item.type)
        onActivated: {
            if (currentValue === "custom") {
                select(item.label ? "label" : item.type)
                const l = kindBox.list, i = kindBox.index
                prompt.ask(plume.t.custom_label_title, "", plume.t.custom_label_ph, item.label || "", plume.t.custom_label_go, text => {
                    const copy = editor[l].slice()
                    copy[i] = Object.assign({}, copy[i], { label: text })
                    editor[l] = copy
                })
            } else if (currentValue !== "label") {
                editor.setAt(list, index, "type", currentValue)
                editor.setAt(list, index, "label", "")
            }
        }
    }

    Rectangle {
        visible: !!editor.info.readonly
        Layout.fillWidth: true
        implicitHeight: copyNote.implicitHeight + 20
        radius: 8
        color: theme.c.tint
        Text {
            id: copyNote
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
            text: plume.t.contact_copy_note.replace("%1", editor.info.bookName || "")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: theme.c.tintText
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 14
        Avatar {
            initials: [given.text, family.text].filter(x => x.trim()).map(x => x.trim()[0].toUpperCase()).join("") || "?"
            tint: editor.info.tint || 0
            photo: editor.shownPhoto
            size: 56
        }
        OButton { kind: "quiet"; iconName: "image"; text: editor.shownPhoto ? plume.t.photo_change : plume.t.photo_choose; onClicked: photoDialog.open() }
        OButton { visible: editor.shownPhoto !== ""; kind: "quiet"; iconName: "trash"; text: plume.t.photo_remove; onClicked: editor.photo = "" }
        Item { Layout.fillWidth: true }
    }
    FileDialog {
        id: photoDialog
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.PicturesLocation)
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.heic)"]
        onAccepted: {
            const data = people.photoFrom(selectedFile.toString())
            if (data) editor.photo = data
            else plume.toast(plume.t.photo_invalid)
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: 10; rowSpacing: 10
        OTextField { id: given; Layout.fillWidth: true; placeholderText: plume.t.first_name; onAccepted: editor.save() }
        OTextField { id: family; Layout.fillWidth: true; placeholderText: plume.t.last_name; onAccepted: editor.save() }
        OTextField { id: org; Layout.fillWidth: true; placeholderText: plume.t.company }
        OTextField { id: job; Layout.fillWidth: true; placeholderText: plume.t.job }
    }

    Label_ { text: plume.t.email_other; Layout.topMargin: 4 }
    Repeater {
        model: editor.emails
        ColumnLayout {
            id: emailRow
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KindBox { list: "emails"; index: emailRow.index; item: emailRow.modelData }
                OTextField {
                    Layout.fillWidth: true; text: emailRow.modelData.value; placeholderText: plume.t.email_ph
                    onEditingFinished: { editor.setAt("emails", emailRow.index, "value", text); editor.checkTaken(emailRow.index, text) }
                }
                OButton { kind: "quiet"; iconName: "close"; iconSize: 16; implicitWidth: 34; Accessible.name: plume.t.delete; onClicked: { const l = editor.emails.slice(); l.splice(emailRow.index, 1); editor.emails = l; editor.taken = ({}) } }
            }
            // this address is already someone's card: say so before a second one is made
            RowLayout {
                visible: !!editor.taken[emailRow.index]
                Layout.leftMargin: 140
                spacing: 8
                Icon { name: "people"; size: 14; color: theme.c.saffronInk }
                Text {
                    text: plume.t.email_taken.replace("%1", (editor.taken[emailRow.index] || {}).name || "")
                    textFormat: Text.PlainText
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: theme.c.saffronInk
                }
                OButton {
                    kind: "quiet"; text: plume.t.open_card
                    onClicked: { const id = editor.taken[emailRow.index].id; editor.close(); editor.openOther(id) }
                }
            }
        }
    }
    OButton { kind: "quiet"; iconName: "plus"; text: plume.t.add_email; onClicked: editor.emails = editor.emails.concat([{ type: "home", value: "" }]) }

    Label_ { text: plume.t.phone_other }
    Repeater {
        model: editor.phones
        RowLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 8
            KindBox { list: "phones"; index: parent.index; item: parent.modelData }
            OTextField { Layout.fillWidth: true; text: modelData.value; placeholderText: plume.t.phone_ph; font.family: "JetBrains Mono"; font.pixelSize: 14; onEditingFinished: editor.setAt("phones", index, "value", text) }
            OButton { kind: "quiet"; iconName: "close"; iconSize: 16; implicitWidth: 34; Accessible.name: plume.t.delete; onClicked: { const l = editor.phones.slice(); l.splice(index, 1); editor.phones = l } }
        }
    }
    OButton { kind: "quiet"; iconName: "plus"; text: plume.t.add_phone; onClicked: editor.phones = editor.phones.concat([{ type: "cell", value: "" }]) }

    Label_ { text: plume.t.address_home; visible: editor.addresses.length > 0 }
    Repeater {
        model: editor.addresses
        GridLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 8; rowSpacing: 8
            KindBox { list: "addresses"; index: parent.index; item: parent.modelData }
            OTextField { Layout.fillWidth: true; text: modelData.street; placeholderText: plume.t.street; onEditingFinished: editor.setAt("addresses", index, "street", text) }
            OButton { kind: "quiet"; iconName: "close"; iconSize: 16; implicitWidth: 34; Accessible.name: plume.t.delete; onClicked: { const l = editor.addresses.slice(); l.splice(index, 1); editor.addresses = l } }
            OTextField { Layout.preferredWidth: 132; text: modelData.code; placeholderText: plume.t.postcode; onEditingFinished: editor.setAt("addresses", index, "code", text) }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                OTextField { Layout.fillWidth: true; text: modelData.city; placeholderText: plume.t.city; onEditingFinished: editor.setAt("addresses", index, "city", text) }
                OTextField { Layout.preferredWidth: 120; text: modelData.region || ""; placeholderText: plume.t.region; onEditingFinished: editor.setAt("addresses", index, "region", text) }
                OTextField { Layout.preferredWidth: 120; text: modelData.country; placeholderText: plume.t.country; onEditingFinished: editor.setAt("addresses", index, "country", text) }
            }
            Item { implicitWidth: 34 }
        }
    }
    OButton { kind: "quiet"; iconName: "plus"; text: plume.t.add_address; onClicked: editor.addresses = editor.addresses.concat([{ type: "home", street: "", city: "", region: "", code: "", country: "" }]) }

    Label_ { text: plume.t.related; visible: editor.related.length > 0 }
    Repeater {
        model: editor.related
        RowLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 8
            OComboBox { Layout.preferredWidth: 132; model: editor.relations; Component.onCompleted: select(modelData.type); onActivated: editor.setAt("related", index, "type", currentValue) }
            OTextField { Layout.fillWidth: true; text: modelData.value; placeholderText: plume.t.related_ph; onEditingFinished: editor.setAt("related", index, "value", text) }
            OButton { kind: "quiet"; iconName: "close"; iconSize: 16; implicitWidth: 34; Accessible.name: plume.t.delete; onClicked: { const l = editor.related.slice(); l.splice(index, 1); editor.related = l } }
        }
    }
    OButton { kind: "quiet"; iconName: "plus"; text: plume.t.add_related; onClicked: editor.related = editor.related.concat([{ type: "spouse", value: "" }]) }

    GridLayout {
        Layout.fillWidth: true
        Layout.topMargin: 4
        columns: 2
        columnSpacing: 10; rowSpacing: 10
        Label_ { text: plume.t.birthday }
        Label_ { text: plume.t.anniversary }
        OTextField { id: bday; Layout.fillWidth: true; placeholderText: plume.t.bday_ph; font.family: "JetBrains Mono"; font.pixelSize: 14; onTextChanged: bdayError.visible = false }
        OTextField { id: anniv; Layout.fillWidth: true; placeholderText: plume.t.bday_ph; font.family: "JetBrains Mono"; font.pixelSize: 14; onTextChanged: annivError.visible = false }
        Text {
            id: bdayError
            visible: false
            Layout.columnSpan: 2
            Layout.fillWidth: true
            text: plume.t.bday_invalid
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: theme.c.danger
        }
        Text {
            id: annivError
            visible: false
            Layout.columnSpan: 2
            Layout.fillWidth: true
            text: plume.t.bday_invalid
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: theme.c.danger
        }
        Label_ { text: plume.t.nickname }
        Label_ { text: plume.t.website }
        OTextField { id: nickname; Layout.fillWidth: true }
        OTextField { id: website; Layout.fillWidth: true; placeholderText: "https://" }
        Label_ { text: plume.t.groups_label }
        Label_ { text: plume.t.book_label }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Flow {
                Layout.fillWidth: true
                visible: editor.groups.length > 0
                spacing: 6
                Repeater {
                    model: editor.groups
                    Rectangle {
                        required property string modelData
                        required property int index
                        height: 28; radius: 14
                        width: groupRow.implicitWidth + 14
                        color: theme.c.okTint
                        Row {
                            id: groupRow
                            anchors.centerIn: parent
                            spacing: 4
                            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.okInk }
                            OButton { anchors.verticalCenter: parent.verticalCenter; kind: "quiet"; iconName: "close"; iconSize: 11; height_: 18; implicitWidth: 18; Accessible.name: plume.t.delete; onClicked: { const l = editor.groups.slice(); l.splice(index, 1); editor.groups = l } }
                        }
                    }
                }
            }
            OTextField {
                Layout.fillWidth: true
                placeholderText: plume.t.groups_ph
                onAccepted: {
                    const g = text.trim()
                    if (g && editor.groups.indexOf(g) === -1) editor.groups = editor.groups.concat([g])
                    text = ""
                }
            }
        }
        OComboBox {
            id: book
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            model: (people.books || []).filter(b => !b.readonly).map(b => ({ text: b.name, value: b.id }))
            Component.onCompleted: select(editor.info.bookId)
        }
    }

    Label_ { text: plume.t.notes }
    OTextArea { id: notes; Layout.fillWidth: true; Layout.preferredHeight: 80 }

    onOpened: book.select(info.readonly ? people.defaultBook : info.bookId || people.defaultBook)

    PromptDialog { id: prompt }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: editor.close() },
        OButton { kind: "primary"; text: plume.t.save; onClicked: editor.save() }
    ]
}
