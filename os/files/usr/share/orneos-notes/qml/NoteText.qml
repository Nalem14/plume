// The note's text: plain Markdown, drawn as one reads it (helper: notes_core.editor), with round boxes over the
// checklist marks and dots over the bullets. What is typed is saved a moment later (and at once when another
// note opens). Return continues a list (renumbered), Tab indents it; in a table, Tab goes to the next cell and the
// columns line up. Ctrl+V of an image attaches it; text copied from a page or a mail keeps its formatting (as
// Markdown; Ctrl+Maj+V: plain). « # » proposes the tags already used; Alt+↑/↓ move lines; a box or a dot drags.
import QtQuick
import QtQuick.Controls
import "components"

Flickable {
    id: flick
    readonly property var c: theme.c
    property string key
    property var helper
    property bool readOnly: false
    property int textSize: app.prefs.text_size || 16
    property real maxWidth: 760
    property alias area: area
    property alias text: area.text
    property bool dirty: false
    property bool loading: false
    property Component header: null
    property Component footer: null
    signal saved()
    signal linkRequested()                   // Ctrl+Maj+K: « Lier à… »
    // « Rechercher dans la note »: what is looked for, its matches (positions) and the one shown
    property string findText: ""
    property var found: []
    property int foundAt: -1
    property real dragY: -1                  // a list item being dragged: where it would go

    contentWidth: width
    contentHeight: column.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    function ensureVisible(r) {
        const top = area.y + r.y - 24, bottom = area.y + r.y + r.height + 48
        if (contentY > top)
            contentY = Math.max(0, top)
        else if (contentY + height < bottom)
            contentY = Math.min(contentHeight - height, bottom - height)
    }

    // ---- loading and saving ----------------------------------------------------------------------------
    function load(content) {
        loading = true
        area.text = content || ""
        loading = false
        dirty = false
        saveTimer.stop()
    }
    function flush() {
        if (dirty && key !== "" && !readOnly)
            renumberAt(area.cursorPosition)
        if (dirty && key !== "") {
            saveTimer.stop()
            dirty = false
            notes.setContent(key, area.text)
            saved()
        }
    }
    // a sync changed the note while it is open: taken in, the cursor kept where it was
    function takeRemote(content) {
        if (dirty || area.text === content)
            return
        // the cursor stays on the same words: moved by what changed before it
        const at = area.cursorPosition, before = area.text
        let same = 0
        while (same < at && same < content.length && before[same] === content[same]) same++
        const shift = same < at ? content.length - before.length : 0
        load(content)
        area.cursorPosition = Math.max(0, Math.min(at + shift, area.length))
        if (findText) refind(false)
    }

    // ---- find (and replace) in the note ----------------------------------------------------------------------
    function refind(move) {
        found = findText ? helper.matches(findText) : []
        if (!found.length) foundAt = -1
        else if (move || foundAt < 0 || found.indexOf(foundAt) < 0) {
            const from = area.selectionStart
            const next = found.find(p => p >= from)
            foundAt = next === undefined ? found[0] : next
        }
        helper.setFind(findText, foundAt)
        if (move && foundAt >= 0) showMatch()
    }
    function setFind(text) { findText = text; refind(true) }
    function findStep(back) {
        if (!found.length) return
        const i = found.indexOf(foundAt)
        foundAt = found[(i + (back ? found.length - 1 : 1)) % found.length]
        helper.setFind(findText, foundAt)
        showMatch()
    }
    function showMatch() {
        area.select(foundAt, foundAt + findText.length)
        ensureVisible(area.positionToRectangle(foundAt))
    }
    function clearFind() { findText = ""; found = []; foundAt = -1; helper.setFind("", -1) }
    function replaceOne(text) {
        if (readOnly || foundAt < 0) return
        replaceRange(foundAt, foundAt + findText.length, text)
        const next = foundAt + text.length
        found = helper.matches(findText)
        const after = found.find(p => p >= next)
        foundAt = after === undefined ? (found.length ? found[0] : -1) : after
        helper.setFind(findText, foundAt)
        if (foundAt >= 0) showMatch()
    }
    function replaceAll(text) {
        if (readOnly || !found.length) return 0
        const count = found.length
        for (let i = found.length - 1; i >= 0; i--)
            replaceRange(found[i], found[i] + findText.length, text)
        refind(false)
        return count
    }
    Timer { id: saveTimer; interval: 500; onTriggered: flick.flush() }

    // ---- editing helpers (all through insert/remove, so Ctrl+Z undoes them) --------------------------------
    function lineStart(pos) { return area.text.lastIndexOf("\n", pos - 1) + 1 }
    function lineEnd(pos) { const i = area.text.indexOf("\n", pos); return i < 0 ? area.text.length : i }
    function lineAt(pos) { return area.text.slice(lineStart(pos), lineEnd(pos)) }
    function replaceRange(from, to, text) {
        area.remove(from, to)
        area.insert(from, text)
    }
    // the lines of the selection (or of the cursor) changed by fn(line, index) → new line
    function mapLines(fn) {
        const from = lineStart(area.selectionStart), to = lineEnd(area.selectionEnd)
        const lines = area.text.slice(from, to).split("\n")
        const out = lines.map((l, i) => fn(l, i))
        const joined = out.join("\n")
        if (joined === lines.join("\n"))
            return
        replaceRange(from, to, joined)
        area.select(from, from + joined.length)
        if (lines.length === 1)
            area.cursorPosition = from + joined.length
    }
    readonly property var listMark: /^(\s*)([-*+] \[[ xX]\] |[-*+] |(\d+)([.)]) |> )(.*)$/
    function stripMark(line) {
        return line.replace(/^(\s*)([-*+] \[[ xX]\] |[-*+] |\d+[.)] |> |#{1,6} )/, "$1")
    }
    function setBlock(kind) {
        mapLines((line, i) => {
            const bare = stripMark(line)
            const indent = bare.match(/^\s*/)[0], body = bare.slice(indent.length)
            if (kind === "body") return indent + body
            if (kind === "title") return "# " + body.trim()
            if (kind === "heading") return "## " + body.trim()
            if (kind === "subheading") return "### " + body.trim()
            if (kind === "bullet") return indent + "- " + body
            if (kind === "number") return indent + (i + 1) + ". " + body
            if (kind === "quote") return indent + "> " + body
            if (kind === "check") return indent + "- [ ] " + body
            return line
        })
        if (kind === "number") renumberAt(area.selectionStart)
    }
    // Ctrl+Shift+L: a checklist, or back to text when it is one already
    function toggleChecklist() {
        const isCheck = /^\s*[-*+] \[[ xX]\] /.test(lineAt(area.cursorPosition))
        setBlock(isCheck ? "body" : "check")
    }
    function wrap(mark, closing) {
        closing = closing === undefined ? mark : closing
        const s = area.selectionStart, e = area.selectionEnd
        const selected = area.text.slice(s, e)
        if (selected.startsWith(mark) && selected.endsWith(closing) && selected.length >= mark.length + closing.length) {
            replaceRange(s, e, selected.slice(mark.length, selected.length - closing.length))
            area.select(s, e - mark.length - closing.length)
            return
        }
        if (area.text.slice(s - mark.length, s) === mark && area.text.slice(e, e + closing.length) === closing) {
            area.remove(e, e + closing.length)
            area.remove(s - mark.length, s)
            area.select(s - mark.length, e - mark.length)
            return
        }
        area.insert(e, closing)
        area.insert(s, mark)
        if (s === e)
            area.cursorPosition = s + mark.length
        else
            area.select(s + mark.length, e + mark.length)
    }
    function insertLink() {
        const s = area.selectionStart, e = area.selectionEnd
        const label = area.text.slice(s, e) || app.t.link_text
        replaceRange(s, e, "[" + label + "](https://)")
        area.select(s + label.length + 3, s + label.length + 11)
    }
    // a link to a mail, a note or a task (dropped, pasted or picked): inline, a space on each side; several
    // come as a list on their own lines
    function insertLinkAt(pos, md) {
        if (readOnly || !md)
            return
        pos = Math.max(0, Math.min(pos, area.length))
        if (md.indexOf("\n") >= 0) {
            const end = lineEnd(pos)
            area.insert(end, (area.text.slice(lineStart(pos), end).trim() ? "\n" : "") + md + "\n")
            return
        }
        const before = pos > 0 && !/\s/.test(area.text[pos - 1]) ? " " : ""
        const after = pos < area.length && !/\s/.test(area.text[pos]) ? " " : ""
        area.insert(pos, before + md + after)
        area.cursorPosition = pos + before.length + md.length + after.length
    }
    // the link of the note under a point ({url, start, end, label} or null): a [label](url) or a bare address
    function linkAt(pos) {
        const line = lineAt(pos), from = lineStart(pos), at = pos - from
        const re = /\[([^\]]*)\]\(([^)\s]+)\)|https?:\/\/[^\s<>()]+/g
        let m
        while ((m = re.exec(line)) !== null) {
            if (at >= m.index && at <= m.index + m[0].length)
                return { url: m[2] || m[0], label: m[1] || "", start: from + m.index, end: from + m.index + m[0].length }
        }
        return null
    }
    function isEntity(url) { return /^orneos:\/\/|\/apps\/notes\/(#\/)?note\/\d+|\/apps\/tasks\/#\/calendars\//.test(url) }
    function insertBlock(text) {
        const at = area.cursorPosition
        const before = area.text.slice(lineStart(at), at).trim() !== "" ? "\n" : ""
        area.insert(lineEnd(at), before + text)
    }
    function insertTable() {
        insertBlock("\n| " + app.t.table_col + " 1 | " + app.t.table_col + " 2 |\n|---|---|\n|  |  |\n")
    }
    function insertAtCursor(text) {
        if (!text)
            return
        const at = area.cursorPosition
        const lead = at > 0 && area.text[at - 1] !== "\n" ? "\n" : ""
        area.insert(at, lead + text + "\n")
    }
    function toggleCheckAt(pos) {
        if (readOnly)
            return
        const open = area.text.indexOf("[", pos)
        if (open < 0 || open > pos + 6)
            return
        const keep = area.cursorPosition
        const now = area.text[open + 1]
        area.remove(open + 1, open + 2)
        area.insert(open + 1, now === " " ? "x" : " ")
        area.cursorPosition = keep
    }

    // ---- numbered lists: 1, 2, 3 again after an item is added, moved or taken out --------------------------------
    readonly property var numbered: /^(\s*)(\d+)([.)])(\s)/
    function renumberAt(pos) {
        const lines = area.text.split("\n")
        let at = 0, index = 0
        for (; index < lines.length; index++) {
            if (at + lines[index].length >= pos) break
            at += lines[index].length + 1
        }
        if (index >= lines.length) return
        const inList = l => /^\s*([-*+]|\d+[.)])\s/.test(l) || (/^\s+\S/.test(l))
        if (!inList(lines[index])) return
        let first = index, last = index
        while (first > 0 && inList(lines[first - 1])) first--
        while (last + 1 < lines.length && inList(lines[last + 1])) last++
        // each level starts from its smallest number (an item moved to the top keeps the list at 1)
        const startAt = {}
        for (const line of lines.slice(first, last + 1)) {
            const m = line.match(numbered)
            if (!m) continue
            const indent = m[1].length
            startAt[indent] = startAt[indent] === undefined ? parseInt(m[2]) : Math.min(startAt[indent], parseInt(m[2]))
        }
        const next = {}
        let changed = false
        const out = lines.slice(first, last + 1).map(line => {
            const m = line.match(numbered)
            const indent = (line.match(/^\s*/)[0]).length
            for (const k in next) if (Number(k) > indent) delete next[k]
            if (!m) { if (/^\s*[-*+]\s/.test(line)) delete next[indent]; return line }
            const n = next[indent] === undefined ? startAt[indent] : next[indent]
            next[indent] = n + 1
            if (n === parseInt(m[2])) return line
            changed = true
            return m[1] + n + m[3] + m[4] + line.slice(m[0].length)
        })
        if (!changed) return
        let start = 0
        for (let i = 0; i < first; i++) start += lines[i].length + 1
        const old = lines.slice(first, last + 1).join("\n"), joined = out.join("\n")
        const keep = area.cursorPosition
        replaceRange(start, start + old.length, joined)
        area.cursorPosition = Math.min(area.length, keep + (keep > start ? joined.length - old.length : 0))
    }

    // ---- tables: Tab to the next cell, Return for a new row, columns lined up ----------------------------------
    function isTable(line) { return /^\s*\|/.test(line) }
    function tableBlock(pos) {
        const lines = area.text.split("\n")
        let at = 0, index = 0
        for (; index < lines.length; index++) {
            if (at + lines[index].length >= pos) break
            at += lines[index].length + 1
        }
        if (index >= lines.length || !isTable(lines[index])) return null
        let first = index, last = index
        while (first > 0 && isTable(lines[first - 1])) first--
        while (last + 1 < lines.length && isTable(lines[last + 1])) last++
        let start = 0
        for (let i = 0; i < first; i++) start += lines[i].length + 1
        return { lines: lines.slice(first, last + 1), start: start, row: index - first }
    }
    function cells(line) {
        let t = line.trim()
        if (t.startsWith("|")) t = t.slice(1)
        if (t.endsWith("|") && !t.endsWith("\\|")) t = t.slice(0, -1)
        return t.split("|").map(c => c.trim())
    }
    function isRule(cellsOf) { return cellsOf.length > 0 && cellsOf.every(c => /^:?-{1,}:?$/.test(c)) }
    // the table rebuilt with its columns lined up; the cursor goes to cell (row, col) when given
    function layoutTable(block, rows, row, col, offset) {
        const width = Math.max(...rows.map(r => r.length))
        rows = rows.map(r => r.concat(Array(width - r.length).fill("")))
        const sizes = []
        for (let c = 0; c < width; c++)
            sizes.push(Math.max(3, ...rows.map(r => isRule(r) ? 3 : r[c].length)))
        const out = rows.map(r => "| " + r.map((cell, c) => {
            if (isRule(r)) {
                const left = cell.startsWith(":"), right = cell.endsWith(":")
                return (left ? ":" : "-") + "-".repeat(sizes[c] - 2) + (right ? ":" : "-")
            }
            return cell + " ".repeat(sizes[c] - cell.length)
        }).join(" | ") + " |")
        const old = block.lines.join("\n"), joined = out.join("\n")
        if (joined !== old)
            replaceRange(block.start, block.start + old.length, joined)
        if (row !== undefined) {
            let at = block.start
            for (let i = 0; i < row; i++) at += out[i].length + 1
            at += 2
            for (let c = 0; c < col; c++) at += sizes[c] + 3
            area.cursorPosition = at + Math.min(offset || 0, rows[row][col].length)
        }
    }
    function cellAt(block, pos) {
        let at = block.start
        for (let i = 0; i < block.row; i++) at += block.lines[i].length + 1
        const line = block.lines[block.row], inLine = pos - at
        const before = line.slice(0, inLine)
        const col = Math.max(0, (before.match(/\|/g) || []).length - (line.trim().startsWith("|") ? 1 : 0))
        const cellStart = before.lastIndexOf("|") + 1
        const raw = line.slice(cellStart, inLine)
        return { col: col, offset: raw.replace(/^\s+/, "").length }
    }
    function tableTab(back) {
        const block = tableBlock(area.cursorPosition)
        if (!block) return false
        const rows = block.lines.map(cells)
        const here = cellAt(block, area.cursorPosition)
        let row = block.row, col = Math.min(here.col, rows[row].length - 1) + (back ? -1 : 1)
        const width = Math.max(...rows.map(r => r.length))
        if (col >= width) { col = 0; row++ }
        if (col < 0) { col = width - 1; row-- }
        while (row >= 0 && row < rows.length && isRule(rows[row])) row += back ? -1 : 1
        if (row < 0) { row = 0; col = 0 }
        if (row >= rows.length) rows.push(Array(width).fill(""))
        layoutTable(block, rows, row, col, 999)
        return true
    }
    function tableReturn() {
        const block = tableBlock(area.cursorPosition)
        if (!block) return false
        const rows = block.lines.map(cells)
        const width = Math.max(...rows.map(r => r.length))
        let row = block.row + 1
        if (row < rows.length && isRule(rows[row])) row++
        rows.splice(row, 0, Array(width).fill(""))
        layoutTable(block, rows, row, 0, 0)
        return true
    }
    function tableEdit(what) {
        const block = tableBlock(area.cursorPosition)
        if (!block) return
        const rows = block.lines.map(cells)
        const width = Math.max(...rows.map(r => r.length))
        const here = cellAt(block, area.cursorPosition)
        let row = block.row, col = Math.min(here.col, width - 1)
        if (what === "row") { rows.splice(row + 1, 0, Array(width).fill("")); row++ }
        else if (what === "column") { rows.forEach(r => r.splice(col + 1, 0, isRule(r) ? "---" : "")); col++ }
        else if (what === "deleteRow" && !isRule(rows[row]) && rows.length > 2) { rows.splice(row, 1); row = Math.min(row, rows.length - 1) }
        else if (what === "deleteColumn" && width > 1) { rows.forEach(r => r.splice(col, 1)); col = Math.max(0, col - 1) }
        if (isRule(rows[row])) row = Math.max(0, row - 1)
        layoutTable(block, rows, row, col, 0)
    }
    function inTable() { return isTable(lineAt(area.cursorPosition)) }

    // ---- checklists ---------------------------------------------------------------------------------------------
    function uncheckAll() {
        let inside = false
        const out = area.text.split("\n").map(l => {
            if (/^\s{0,3}(```|~~~)/.test(l)) { inside = !inside; return l }
            return inside ? l : l.replace(/^(\s*[-*+]\s+\[)[xX](\]\s)/, "$1 $2")
        }).join("\n")
        if (out !== area.text) { replaceRange(0, area.length, out); return true }
        return false
    }
    // the items checked go to the end of their list, with what is indented under them
    function checkedDown() {
        const lines = area.text.split("\n")
        const check = /^(\s*)[-*+]\s+\[([ xX])\]\s/
        let i = 0, changed = false
        while (i < lines.length) {
            if (!check.test(lines[i]) || lines[i].match(/^\s*/)[0].length) { i++; continue }
            const groups = []
            while (i < lines.length && check.test(lines[i]) && !lines[i].match(/^\s*/)[0].length) {
                const g = [lines[i]]
                i++
                while (i < lines.length && /^\s+\S/.test(lines[i])) g.push(lines[i++])
                groups.push(g)
            }
            const open = groups.filter(g => / \[ \]/.test(g[0].slice(0, 8)))
            const done = groups.filter(g => !/ \[ \]/.test(g[0].slice(0, 8)))
            const sorted = open.concat(done)
            if (sorted.some((g, k) => g !== groups[k])) {
                changed = true
                const flat = [].concat(...sorted)
                lines.splice(i - flat.length, flat.length, ...flat)
            }
        }
        if (changed) replaceRange(0, area.length, lines.join("\n"))
        return changed
    }

    // ---- moving lines: Alt+↑/↓, or a list item dragged by its box or dot ----------------------------------------
    function lineIndex(lines, pos) {
        let at = 0
        for (let i = 0; i < lines.length; i++) {
            if (at + lines[i].length >= pos) return i
            at += lines[i].length + 1
        }
        return lines.length - 1
    }
    function offsetOf(lines, index) { let at = 0; for (let i = 0; i < index; i++) at += lines[i].length + 1; return at }
    function moveLines(down) {
        const lines = area.text.split("\n")
        const a = lineIndex(lines, area.selectionStart), b = lineIndex(lines, area.selectionEnd)
        if (down ? b + 1 >= lines.length : a === 0) return
        const cursorLine = lineIndex(lines, area.cursorPosition)
        const inCursor = area.cursorPosition - offsetOf(lines, cursorLine)
        const original = lines.slice()
        const block = lines.splice(a, b - a + 1)
        const to = down ? a + 1 : a - 1
        lines.splice(to, 0, ...block)
        const from = Math.min(a, to), until = Math.max(b, to + block.length - 1)
        const start = offsetOf(original, from)
        const old = original.slice(from, until + 1).join("\n")
        replaceRange(start, start + old.length, lines.slice(from, until + 1).join("\n"))
        const now = to + (cursorLine - a)
        area.cursorPosition = offsetOf(lines, now) + Math.min(inCursor, lines[now].length)
        renumberAt(area.cursorPosition)
    }
    function dropItem(fromPos, y) {
        dragY = -1
        if (readOnly) return
        const lines = area.text.split("\n")
        const from = lineIndex(lines, fromPos)
        const indent = lines[from].match(/^\s*/)[0].length
        let end = from
        while (end + 1 < lines.length && lines[end + 1].trim() !== "" && lines[end + 1].match(/^\s*/)[0].length > indent) end++
        let target = lineIndex(lines, area.positionAt(area.leftPadding + 40, Math.max(0, y)))
        if (target >= from && target <= end) return
        const group = lines.slice(from, end + 1)
        const rest = lines.slice(0, from).concat(lines.slice(end + 1))
        const indentOf = l => l.match(/^\s*/)[0].length
        let at = target
        if (target > end) {
            // going down: after the item dropped on, and after what is indented under it
            at = target - group.length + 1
            const base = indentOf(lines[target])
            while (at < rest.length && rest[at].trim() !== "" && indentOf(rest[at]) > base) at++
        }
        rest.splice(at, 0, ...group)
        const low = Math.min(from, at), high = Math.max(end, at + group.length - 1)
        const start = offsetOf(lines, low)
        const old = lines.slice(low, high + 1).join("\n")
        replaceRange(start, start + old.length, rest.slice(low, high + 1).join("\n"))
        area.cursorPosition = offsetOf(rest, at) + rest[at].length
        renumberAt(area.cursorPosition)
    }

    // ---- « # »: the tags already used -----------------------------------------------------------------------------
    property var tagChoices: []
    property int tagPick: 0
    property int tagFrom: -1
    function updateTags() {
        if (readOnly || !area.activeFocus || area.selectionStart !== area.selectionEnd) { tagChoices = []; return }
        const at = area.cursorPosition
        const before = area.text.slice(lineStart(at), at)
        const m = before.match(/(^|\s)#([^\s#`()\[\]]{1,40})$/)
        if (!m) { tagChoices = []; return }
        const typed = m[2].toLowerCase()
        tagFrom = at - m[2].length
        tagChoices = notes.allTags.map(t => t.tag).filter(t => t.startsWith(typed) && t !== typed).slice(0, 6)
        tagPick = 0
    }
    function takeTag(i) {
        const tag = tagChoices[i]
        if (!tag) return
        const after = area.text[area.cursorPosition] === " " ? "" : " "
        replaceRange(tagFrom, area.cursorPosition, tag + after)
        area.cursorPosition = tagFrom + tag.length + 1
        tagChoices = []
    }

    function continueList(event) {
        const at = area.cursorPosition
        const line = area.text.slice(lineStart(at), at)
        const m = line.match(listMark)
        if (!m || area.selectionStart !== area.selectionEnd) {
            event.accepted = false
            return
        }
        const indent = m[1], mark = m[2], rest = lineAt(at).slice(indent.length + mark.length)
        if (rest.trim() === "" && line.length === indent.length + mark.length) {
            // Return on an empty item ends the list
            replaceRange(lineStart(at), lineEnd(at), indent.length >= 2 ? indent.slice(2) + mark : "")
            event.accepted = true
            return
        }
        let next = mark
        if (/\[[ xX]\]/.test(mark)) next = mark.replace(/\[[xX]\]/, "[ ]")
        else if (m[3]) next = (parseInt(m[3]) + 1) + m[4] + " "
        area.insert(at, "\n" + indent + next)
        event.accepted = true
    }
    function indentList(back) {
        const line = lineAt(area.cursorPosition)
        if (!listMark.test(line))
            return false
        mapLines(l => back ? l.replace(/^ {1,2}|^\t/, "") : "  " + l)
        return true
    }

    // ---- the page ------------------------------------------------------------------------------------------
    Column {
        id: column
        width: flick.width
        Loader { width: parent.width; sourceComponent: flick.header; active: flick.header !== null }

        TextArea {
            id: area
            readonly property real side: Math.max(28, (flick.width - flick.maxWidth) / 2)
            property int layoutTick: 0
            width: parent.width
            leftPadding: side; rightPadding: side
            topPadding: 6; bottomPadding: 28
            readOnly: flick.readOnly
            wrapMode: TextEdit.Wrap
            textFormat: TextEdit.PlainText
            selectByMouse: true
            persistentSelection: true
            color: flick.c.body
            selectionColor: flick.c.tint
            selectedTextColor: flick.c.text
            placeholderText: flick.readOnly ? "" : app.t.placeholder
            placeholderTextColor: flick.c.faint
            font.family: "Schibsted Grotesk"
            font.pixelSize: flick.textSize
            background: null
            Component.onCompleted: if (flick.helper) flick.helper.attach(area.textDocument, flick.textSize)
            onTextChanged: {
                if (!flick.loading && !flick.readOnly) {
                    flick.dirty = true
                    saveTimer.restart()
                }
                if (flick.findText) findTimer.restart()
            }
            Timer { id: findTimer; interval: 150; onTriggered: flick.refind(false) }
            onCursorRectangleChanged: if (activeFocus) flick.ensureVisible(cursorRectangle)
            onCursorPositionChanged: { if (flick.helper && activeFocus) flick.helper.setCursor(cursorPosition); Qt.callLater(flick.updateTags) }
            onActiveFocusChanged: if (flick.helper) flick.helper.setCursor(activeFocus ? cursorPosition : -1)
            onContentHeightChanged: layoutTick++
            onWidthChanged: layoutTick++
            Connections {
                target: flick
                function onTextSizeChanged() { if (flick.helper) flick.helper.setSize(flick.textSize); area.layoutTick++ }
            }
            Connections {
                target: flick.helper
                function onMarksChanged() { Qt.callLater(() => area.layoutTick++) }
            }

            function handleReturn(event) {
                if (flick.tagChoices.length) { flick.takeTag(flick.tagPick); event.accepted = true; return }
                if (!flick.readOnly && !(event.modifiers & Qt.ShiftModifier) && flick.inTable()) { event.accepted = flick.tableReturn(); return }
                flick.continueList(event)
                if (event.accepted) flick.renumberAt(area.cursorPosition)
            }
            Keys.onReturnPressed: event => handleReturn(event)
            Keys.onEnterPressed: event => handleReturn(event)
            Keys.onTabPressed: event => {
                if (flick.tagChoices.length) { flick.takeTag(flick.tagPick); event.accepted = true; return }
                if (flick.readOnly) { event.accepted = false; return }
                if (flick.tableTab(false)) { event.accepted = true; return }
                event.accepted = flick.indentList(false) || (area.insert(area.cursorPosition, "\t"), true)
                flick.renumberAt(area.cursorPosition)
            }
            Keys.onBacktabPressed: event => {
                if (flick.readOnly) { event.accepted = false; return }
                if (flick.tableTab(true)) { event.accepted = true; return }
                event.accepted = flick.indentList(true)
                flick.renumberAt(area.cursorPosition)
            }
            Keys.onUpPressed: event => {
                if (flick.tagChoices.length) { flick.tagPick = (flick.tagPick + flick.tagChoices.length - 1) % flick.tagChoices.length; event.accepted = true }
                else if ((event.modifiers & Qt.AltModifier) && !flick.readOnly) { flick.moveLines(false); event.accepted = true }
                else event.accepted = false
            }
            Keys.onDownPressed: event => {
                if (flick.tagChoices.length) { flick.tagPick = (flick.tagPick + 1) % flick.tagChoices.length; event.accepted = true }
                else if ((event.modifiers & Qt.AltModifier) && !flick.readOnly) { flick.moveLines(true); event.accepted = true }
                else event.accepted = false
            }
            Keys.onEscapePressed: event => {
                if (flick.tagChoices.length) { flick.tagChoices = []; event.accepted = true }
                else event.accepted = false
            }
            // the editor's own keys go before the shortcuts of the window around it (Plume: Ctrl+K is its palette)
            Keys.onShortcutOverride: event => {
                if (flick.readOnly) return
                const ctrl = event.modifiers & Qt.ControlModifier, shift = event.modifiers & Qt.ShiftModifier
                if (ctrl && [Qt.Key_B, Qt.Key_I, Qt.Key_K].indexOf(event.key) >= 0) event.accepted = true
                else if (ctrl && shift && [Qt.Key_X, Qt.Key_L, Qt.Key_T, Qt.Key_H, Qt.Key_7, Qt.Key_8, Qt.Key_V].indexOf(event.key) >= 0) event.accepted = true
                else if ((event.modifiers & Qt.AltModifier) && (event.key === Qt.Key_Up || event.key === Qt.Key_Down)) event.accepted = true
            }
            Keys.onPressed: event => {
                const ctrl = event.modifiers & Qt.ControlModifier, shift = event.modifiers & Qt.ShiftModifier
                if (event.matches(StandardKey.Paste) && !flick.readOnly) {
                    const link = notes.pasteLinks(flick.key)
                    if (link) {
                        if (area.selectionStart !== area.selectionEnd) area.remove(area.selectionStart, area.selectionEnd)
                        flick.insertLinkAt(area.cursorPosition, link)
                        event.accepted = true
                        return
                    }
                    const md = notes.pasteImage(flick.key)
                    if (md) { flick.insertAtCursor(md); event.accepted = true; return }
                    // a page, a mail, a document: their titles, bold, lists and links come as Markdown
                    const rich = notes.pasteRich()
                    if (rich) {
                        if (area.selectionStart !== area.selectionEnd) area.remove(area.selectionStart, area.selectionEnd)
                        area.insert(area.cursorPosition, rich)
                        event.accepted = true
                    }
                    return
                }
                if (!ctrl || flick.readOnly) return
                if (shift && event.key === Qt.Key_V) { area.paste(); event.accepted = true; return }
                if (event.key === Qt.Key_B) { flick.wrap("**"); event.accepted = true }
                else if (event.key === Qt.Key_I) { flick.wrap("*"); event.accepted = true }
                else if (shift && event.key === Qt.Key_K) { flick.linkRequested(); event.accepted = true }
                else if (event.key === Qt.Key_K) { flick.insertLink(); event.accepted = true }
                else if (shift && event.key === Qt.Key_X) { flick.wrap("~~"); event.accepted = true }
                else if (shift && event.key === Qt.Key_L) { flick.toggleChecklist(); event.accepted = true }
                else if (shift && event.key === Qt.Key_T) { flick.setBlock("title"); event.accepted = true }
                else if (shift && event.key === Qt.Key_H) { flick.setBlock("heading"); event.accepted = true }
                else if (shift && event.key === Qt.Key_B) { flick.setBlock("body"); event.accepted = true }
                else if (shift && event.key === Qt.Key_7) { flick.setBlock("number"); event.accepted = true }
                else if (shift && event.key === Qt.Key_8) { flick.setBlock("bullet"); event.accepted = true }
            }

            // links open with Ctrl+click (a plain click places the cursor, as in any editor); a link to a mail,
            // a note or a task (a chip) opens with a plain click too, like on macOS
            TapHandler {
                acceptedModifiers: Qt.ControlModifier
                onTapped: (point) => {
                    const link = flick.linkAt(area.positionAt(point.position.x, point.position.y))
                    if (!link) return
                    if (/^https?:|^mailto:|^orneos:/.test(link.url)) notes.openLink(link.url)
                    else notes.openImage(flick.key, decodeURIComponent(link.url))
                }
            }
            // round boxes over "- [ ] " and dots over "- "
            Repeater {
                model: flick.helper ? flick.helper.marks : []
                delegate: Item {
                    id: mark
                    required property var modelData
                    readonly property rect r: { area.layoutTick; return area.positionToRectangle(modelData.pos) }
                    readonly property bool link: modelData.kind === "link" || modelData.kind === "image"
                    readonly property bool image: modelData.kind === "image"
                    readonly property bool check: modelData.kind !== "bullet" && !link
                    readonly property bool done: modelData.kind === "done"
                    x: r.x + (check ? 0 : 2)
                    y: r.y
                    width: check ? 22 : 12
                    height: r.height
                    Rectangle {
                        visible: mark.check
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(flick.textSize * 1.15); height: width; radius: width / 2
                        color: mark.done ? flick.c.saffron : "transparent"
                        border.width: mark.done ? 0 : 1.5
                        border.color: boxHover.hovered ? flick.c.accent : flick.c.faint
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Icon {
                            anchors.centerIn: parent
                            visible: mark.done
                            name: "check"; size: parent.width * 0.7; color: flick.c.saffronText
                        }
                        HoverHandler { id: boxHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: flick.toggleCheckAt(mark.modelData.pos) }
                    }
                    Rectangle {
                        visible: !mark.check && !mark.link
                        anchors.verticalCenter: parent.verticalCenter
                        width: 6; height: 6; radius: 3
                        color: flick.c.accent
                    }
                    // a box or a dot drags its item (and what is indented under it) to another line of the list
                    DragHandler {
                        id: reorder
                        enabled: !flick.readOnly && !mark.link
                        target: null
                        xAxis.enabled: false
                        cursorShape: Qt.ClosedHandCursor
                        onTranslationChanged: if (active) flick.dragY = mark.r.y + mark.r.height / 2 + translation.y
                        onActiveChanged: if (!active && flick.dragY >= 0) flick.dropItem(mark.modelData.pos, flick.dragY)
                    }
                    // the icon of a linked mail, note or task, in the room its chip keeps
                    Icon {
                        visible: mark.link
                        anchors.verticalCenter: parent.verticalCenter
                        name: mark.modelData.icon || "link"
                        size: Math.round(flick.textSize * 0.85)
                        color: flick.c.tintText
                    }
                    // the chip (icon and title) takes the click above the text (an image's: the picture opens): it opens what it links, with a
                    // hand, and the cursor stays where it was (the note does not switch to editing), as on macOS
                    MouseArea {
                        visible: mark.link
                        readonly property var chip: { area.layoutTick; return mark.link ? flick.linkAt(mark.modelData.pos + (mark.image ? 2 : 1)) : null }
                        readonly property rect end: { area.layoutTick; return chip ? area.positionToRectangle(chip.start + 1 + chip.label.length) : Qt.rect(0, 0, 0, 0) }
                        x: 0; y: 0
                        width: Math.max(mark.width, end.y === mark.r.y ? end.x - mark.r.x : area.width - mark.r.x)
                        height: mark.height
                        cursorShape: Qt.PointingHandCursor
                        onClicked: mark.image ? notes.openAttachment(flick.key, mark.modelData.url) : notes.openLink(mark.modelData.url)
                    }
                }
            }
        }

        Loader { width: parent.width; sourceComponent: flick.footer; active: flick.footer !== null }
    }

    // where a dragged item would go
    Rectangle {
        visible: flick.dragY >= 0
        readonly property rect at: area.positionToRectangle(area.positionAt(area.leftPadding + 40, Math.max(0, flick.dragY)))
        x: area.leftPadding - 6; width: area.width - area.leftPadding - area.rightPadding + 12
        y: column.y + area.y + at.y + (flick.dragY > at.y + at.height / 2 ? at.height : 0) - 1
        height: 2; radius: 1
        color: flick.c.accent
    }

    // the tags already used, under the « #… » being typed
    Rectangle {
        id: tagPopup
        visible: flick.tagChoices.length > 0
        readonly property rect at: { area.layoutTick; return area.cursorRectangle }
        x: Math.min(area.x + at.x, flick.width - width - 8)
        y: area.y + at.y + at.height + 4
        z: 10
        width: 220
        height: tagColumn.implicitHeight + 8
        radius: 10
        color: flick.c.overlay
        border.width: 1; border.color: flick.c.overlayLine
        Column {
            id: tagColumn
            x: 4; y: 4
            width: parent.width - 8
            Repeater {
                model: flick.tagChoices
                Rectangle {
                    required property string modelData
                    required property int index
                    width: tagColumn.width; height: 30; radius: 7
                    color: index === flick.tagPick ? flick.c.tint : (tagHover.hovered ? flick.c.hover : "transparent")
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 10
                        text: "#" + parent.modelData
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: index === flick.tagPick ? flick.c.tintText : flick.c.text
                    }
                    HoverHandler { id: tagHover }
                    TapHandler { onTapped: flick.takeTag(parent.index) }
                }
            }
        }
    }

    // a click under the text puts the cursor at its end
    TapHandler {
        enabled: !flick.readOnly
        onTapped: point => {
            if (point.position.y > column.implicitHeight - 20) {
                area.forceActiveFocus()
                area.cursorPosition = area.length
            }
        }
    }
}
