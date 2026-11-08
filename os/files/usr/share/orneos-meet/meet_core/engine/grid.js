// The tiles of a call: one per person (and one per shared screen), us included. Mosaic by default; "speaker"
// puts the shared screen, the pinned person or the last one who spoke in the middle, the others in a strip.
'use strict'

const MIC_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.7"/><path d="M19 11a7 7 0 0 1-1.2 3.9M5 11a7 7 0 0 0 11.2 5.6M12 18v3"/></svg>'

class Grid {
    constructor(root, call) {
        this.root = root
        this.call = call
        this.tiles = new Map()        // key -> element
        this.layout = 'grid'
        this.pinned = ''
        this.lastSpeaker = ''
    }

    setLayout(layout) {
        this.layout = layout === 'speaker' ? 'speaker' : 'grid'
        this.update()
    }

    pin(session) {
        this.pinned = this.pinned === session ? '' : session
        this.update()
    }

    // what to show: [{key, session, stream, name, self, screen, audio, video, speaking, hand, state}]
    items() {
        const call = this.call
        const own = call.signaling ? call.signaling.sessionId : ''
        const list = []
        list.push({
            key: 'self', session: own, stream: call.local, self: true, name: call.nick,
            audio: call.audioOn, video: call.videoOn && call.hasVideo(), speaking: call.speaking, hand: call.hand,
        })
        if (call.screen) list.push({ key: 'self|screen', session: own, stream: call.screen, self: true, screen: true, name: call.nick })
        call.users.forEach((user, session) => {
            if (session === own || !user.inCall) return
            const peer = call.peers.get(session + '|video')
            const hasVideo = !!(peer && peer.stream.getVideoTracks().some((t) => !t.muted))
            list.push({
                key: session, session, stream: peer ? peer.stream : null, name: user.name || call.people[user.userId] || '',
                userId: user.userId, audio: !!user.audio, video: !!user.video && hasVideo, speaking: !!user.speaking,
                hand: !!user.hand, state: peer ? peer.state : 'waiting',
            })
            const screen = call.peers.get(session + '|screen')
            if (screen) list.push({ key: session + '|screen', session, stream: screen.stream, screen: true, name: user.name || '' })
            if (user.speaking) this.lastSpeaker = session
        })
        return list
    }

    update() {
        const items = this.items()
        const seen = new Set()
        items.forEach((item) => {
            seen.add(item.key)
            let tile = this.tiles.get(item.key)
            if (!tile) {
                tile = this.make(item)
                this.tiles.set(item.key, tile)
            }
            this.fill(tile, item)
        })
        this.tiles.forEach((tile, key) => {
            if (!seen.has(key)) {
                tile.remove()
                this.tiles.delete(key)
            }
        })
        this.arrange(items)
    }

    make(item) {
        const tile = document.createElement('div')
        tile.className = 'tile'
        tile.innerHTML = '<video autoplay playsinline></video><div class="avatar"></div>' +
            '<div class="label"><span class="mic"></span><span class="name"></span></div>'
        const video = tile.querySelector('video')
        video.muted = !!item.self          // never hear ourselves
        if (this.call.outputId && video.setSinkId) video.setSinkId(this.call.outputId).catch(() => {})
        tile.addEventListener('dblclick', () => this.pin(item.key))
        // right click: the menu of this person around the call (pin, mute for a moderator, write), in QML
        tile.addEventListener('contextmenu', (e) => {
            e.preventDefault()
            const u = this.call.users.get(item.session) || {}
            this.call.emit({ type: 'tileMenu', key: item.key, session: item.session || '', self: !!item.self,
                             screen: !!item.screen, pinned: this.pinned === item.key, name: item.name || '',
                             userId: u.userId || '', audio: !!item.audio, x: e.clientX, y: e.clientY })
        })
        return tile
    }

    fill(tile, item) {
        const video = tile.querySelector('video')
        if (item.stream && video.srcObject !== item.stream) video.srcObject = item.stream
        if (!item.stream && video.srcObject) video.srcObject = null
        tile.classList.toggle('self', !!item.self && !item.screen)
        tile.classList.toggle('screen', !!item.screen)
        tile.classList.toggle('novideo', !item.screen && !item.video)
        tile.classList.toggle('speaking', !!item.speaking && !item.screen)
        const name = item.screen ? Grid.text('screenOf', { name: item.name || '' }) : (item.self ? Grid.text('you') : (item.name || Grid.text('guest')))
        tile.querySelector('.name').textContent = name
        tile.querySelector('.mic').innerHTML = item.screen || item.audio ? '' : '<span class="muted">' + MIC_OFF + '</span>'
        const avatar = tile.querySelector('.avatar')
        const pic = item.self ? this.call.config.selfAvatar : (this.call.config.avatars || {})[item.userId]
        if (pic) {
            avatar.style.backgroundImage = 'url(' + pic + ')'
            avatar.textContent = ''
        } else {
            avatar.style.backgroundImage = ''
            avatar.textContent = Grid.initials(item.self ? this.call.nick : item.name)
        }
        let hand = tile.querySelector('.hand')
        if (item.hand && !hand) {
            hand = document.createElement('div')
            hand.className = 'hand'
            hand.textContent = '✋ ' + Grid.text('hand')
            tile.appendChild(hand)
        } else if (!item.hand && hand) {
            hand.remove()
        }
        let state = tile.querySelector('.state')
        const waiting = !item.self && !item.screen && (item.state === 'checking' || item.state === 'disconnected' || item.state === 'failed')
        if (waiting && !state) {
            state = document.createElement('div')
            state.className = 'state'
            tile.appendChild(state)
        }
        if (waiting) state.textContent = Grid.text(item.state === 'checking' ? 'connecting' : 'reconnecting')
        else if (state) state.remove()
    }

    arrange(items) {
        const root = this.root
        const others = items.filter((i) => !i.self || i.screen)
        const main = this.mainItem(items)
        root.classList.toggle('speaker', this.layout === 'speaker' || !!main)
        if ((this.layout === 'speaker' || main) && items.length > 1) {
            const focus = main || items.find((i) => i.key === this.lastSpeaker) || others[0] || items[0]
            root.innerHTML = ''
            const big = this.tiles.get(focus.key)
            big.classList.add('main')
            big.style.aspectRatio = 'auto'
            big.style.gridColumn = ''
            root.style.gridTemplateColumns = '1fr'
            root.style.gridAutoRows = ''
            root.appendChild(big)
            const strip = document.createElement('div')
            strip.className = 'strip'
            items.forEach((i) => {
                if (i.key === focus.key) return
                const t = this.tiles.get(i.key)
                t.classList.remove('main')
                t.style.aspectRatio = ''
                t.style.gridColumn = ''
                strip.appendChild(t)
            })
            root.appendChild(strip)
            this.alone(false)
            return
        }
        root.innerHTML = ''
        const n = items.length
        // the room the tiles have: the stage less its padding (under the QML head and bar) and the gaps, read from
        // the CSS so the rows never grow taller than the stage (they would cover one another)
        const css = getComputedStyle(root)
        const gap = parseFloat(css.columnGap) || 0
        const w = root.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight)
        const h = root.clientHeight - parseFloat(css.paddingTop) - parseFloat(css.paddingBottom)
        // the number of columns that makes the tiles (16:9) the biggest
        let best = 1, size = 0
        for (let cols = 1; cols <= n; cols++) {
            const rows = Math.ceil(n / cols)
            const tileW = Math.min((w - (cols - 1) * gap) / cols, ((h - (rows - 1) * gap) / rows) * 16 / 9)
            if (tileW > size) { size = tileW; best = cols }
        }
        const tileW = Math.max(80, Math.floor(size)), tileH = Math.floor(tileW * 9 / 16)
        // half columns, each tile spans two: an incomplete last row starts half a tile further per missing tile, centred
        root.style.gridTemplateColumns = `repeat(${best * 2}, ${(tileW - gap) / 2}px)`
        root.style.gridAutoRows = `${tileH}px`
        const lastRow = n - (n % best || best)
        const alone = n === 1 && this.call.inCall
        items.forEach((i, idx) => {
            const t = this.tiles.get(i.key)
            t.classList.remove('main')
            t.classList.toggle('pip', alone)
            t.style.aspectRatio = ''
            t.style.gridColumn = idx === lastRow && n % best ? `${best - (n % best) + 1} / span 2` : 'span 2'
            root.appendChild(t)
        })
        this.alone(alone)
    }

    mainItem(items) {
        if (this.pinned) {
            const pinned = items.find((i) => i.key === this.pinned)
            if (pinned) return pinned
        }
        return items.find((i) => i.screen && !i.self) || items.find((i) => i.screen) || null
    }

    alone(on) {
        let el = document.querySelector('.alone')
        if (on && !el) {
            el = document.createElement('div')
            el.className = 'alone'
            el.innerHTML = '<strong></strong><span></span>'
            el.querySelector('strong').textContent = Grid.text('aloneTitle')
            el.querySelector('span').textContent = Grid.text('aloneBody')
            document.body.appendChild(el)
        } else if (!on && el) {
            el.remove()
        }
    }

    reaction(session, emoji) {
        const key = session === (this.call.signaling && this.call.signaling.sessionId) ? 'self' : session
        const tile = this.tiles.get(key)
        if (!tile) return
        const el = document.createElement('div')
        el.className = 'reaction'
        el.textContent = emoji
        el.style.marginLeft = (Math.random() * 60 - 30) + 'px'
        tile.appendChild(el)
        setTimeout(() => el.remove(), 2700)
    }

    static initials(name) {
        const parts = String(name || '').replace(/[._]/g, ' ').split(/\s+/).filter(Boolean)
        if (!parts.length) return '?'
        return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    }

    static text(key, vars) {
        let s = (Grid.labels && Grid.labels[key]) || key
        Object.keys(vars || {}).forEach((k) => { s = s.replace('{' + k + '}', vars[k]) })
        return s
    }
}

window.Grid = Grid
window.addEventListener('resize', () => { if (window.call) window.call.view.update() })
