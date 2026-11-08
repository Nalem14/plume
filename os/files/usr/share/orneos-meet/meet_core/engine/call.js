// The call itself, in Chromium's WebRTC (QtWebEngine): our camera and microphone, what we publish to the SFU
// (Janus, behind the signaling server), what we receive from the others, the screen share and the small states
// (muted, speaking, hand raised, reactions). It speaks to Python through QWebChannel ("bridge"):
//   bridge.config            JSON: {settings, token, ncSession, nick, userId, audio, video, people}
//   bridge.event(json)       what happened (state, joined, error, reaction…), for the QML around the call
//   bridge.command(json)     what to do (inCall, audio, video, screen, hand, reaction, leave, devices…)
// Compatible with Talk (web, Android, iOS, desktop): same messages, same flags, same data channel ("status").
'use strict'

const IN_CALL = 1, WITH_AUDIO = 2, WITH_VIDEO = 4
const RETRY_MS = 10000

class Call {
    constructor(bridge, config) {
        this.bridge = bridge
        this.config = config
        this.nick = config.nick || ''
        this.people = config.people || {}             // userId -> display name (from the conversation)
        this.local = null                             // MediaStream (camera + microphone)
        this.screen = null                            // MediaStream (screen share)
        this.audioOn = config.audio !== false
        this.videoOn = config.video !== false
        this.hand = false
        this.speaking = false
        this.inCall = false
        this.publisher = null                         // {pc, dc, sid, retry} for "video"
        this.screenPublisher = null                   // same, for "screen"
        this.peers = new Map()                        // `${session}|${roomType}` -> {pc, stream, dc, sid}
        this.users = new Map()                        // session -> {userId, name, inCall, audio, video, speaking, hand, …}
        this.retries = new Map()                      // session -> interval asking again for an offer
        this.view = new Grid(document.getElementById('stage'), this)
        this.signaling = null
        this.levelTimer = null
        this.ice = config.settings ? this.iceServers(config.settings) : []
    }

    // ---- life ------------------------------------------------------------------------------------------------
    // the camera and microphone first: without the cloud's settings yet, the page is the check before the call
    // (« Prêt à rejoindre ? »): our picture, the level of the microphone; « connect » brings the settings
    async start() {
        document.body.classList.toggle('preview', !this.config.settings)
        this.media = this.openMedia()
        await this.media
        if (this.left) return
        if (this.config.blur && this.config.vision && this.hasVideo()) Blur.set(this, 'blur', this.config.vision)
        if (this.config.settings) this.connect()
        else this.render()
    }

    async connect(data) {
        if (this.signaling || this.connecting) return
        this.connecting = true
        await this.media                  // « connect » may come before the camera is open
        if (this.left) return
        if (data) {
            Object.assign(this.config, { settings: data.settings, ncSession: data.ncSession, nick: data.nick || this.nick })
            this.nick = this.config.nick || this.nick
            this.ice = this.iceServers(data.settings)
        }
        document.body.classList.remove('preview')
        this.signaling = new Signaling(this.config.settings, {
            connected: (resumed) => {
                // the same session again: nothing was lost; a new one: the room is entered again (roomJoined)
                if (resumed) { this.reconnecting = false; this.render() }
                this.emit({ type: 'connected', resumed })
            },
            lost: () => { this.reconnecting = true; this.render(); this.emit({ type: 'reconnecting' }) },
            error: (code, scope) => this.emit({ type: 'error', code, room: scope === 'room' }),
            event: (event) => this.onEvent(event),
            message: (message) => this.onMessage(message),
        })
        this.signaling.connect()
        this.signaling.joinRoom(this.config.token, this.config.ncSession)
        this.render()
    }

    // Python joined the call (POST /call): publish what we have, ask the others for theirs
    enterCall() {
        this.inCall = true
        this.publish()
        this.users.forEach((user, session) => {
            if (user.inCall) this.subscribe(session, user)
        })
        this.render()
    }

    leave() {
        this.inCall = false
        this.left = true
        this.retries.forEach((timer) => clearInterval(timer))
        this.retries.clear()
        this.peers.forEach((peer) => this.closePeer(peer))
        this.peers.clear()
        this.stopPublisher('publisher')
        this.stopPublisher('screenPublisher')
        if (this.screen) this.screen.getTracks().forEach((t) => t.stop())
        if (Blur.active) Blur.stop(this, true)?.stop()
        if (this.local) this.local.getTracks().forEach((t) => t.stop())
        if (this.levelTimer) clearInterval(this.levelTimer)
        if (this.audioContext) this.audioContext.close().catch(() => {})
        if (this.signaling) {
            this.signaling.leaveRoom()
            this.signaling.close()
        }
        this.emit({ type: 'left' })
    }

    emit(data) {
        this.bridge.event(JSON.stringify(data))
    }

    iceServers(settings) {
        const servers = []
        ;(settings.stunservers || []).forEach((s) => servers.push({ urls: s.urls }))
        ;(settings.turnservers || []).forEach((s) => servers.push({ urls: s.urls, username: s.username, credential: s.credential }))
        return servers
    }

    // ---- our camera and microphone ---------------------------------------------------------------------------
    async openMedia() {
        const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        if (this.config.mic) audio.deviceId = { exact: this.config.mic }
        const video = { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } }
        if (this.config.camera) video.deviceId = { exact: this.config.camera }
        const tries = [{ audio, video }, { audio, video: false }, { audio: false, video }]
        for (const constraints of tries) {
            try {
                this.local = await navigator.mediaDevices.getUserMedia(constraints)
                if (this.left) {          // hung up while the system asked for the camera: let it go at once
                    this.local.getTracks().forEach((t) => t.stop())
                    return ''
                }
                break
            } catch (e) {
                this.local = null
            }
        }
        if (!this.local) {
            this.local = new MediaStream()
            this.emit({ type: 'error', code: 'no_media' })
        }
        if (!this.local.getVideoTracks().length) this.videoOn = false
        if (!this.local.getAudioTracks().length) this.audioOn = false
        this.applyMute()
        this.watchLevel()
        this.devices()
    }

    hasAudio() {
        return this.local && this.local.getAudioTracks().length > 0
    }

    hasVideo() {
        return this.local && this.local.getVideoTracks().length > 0
    }

    flags() {
        let flags = IN_CALL
        if (this.hasAudio()) flags |= WITH_AUDIO
        if (this.hasVideo()) flags |= WITH_VIDEO
        return flags
    }

    applyMute() {
        if (!this.local) return
        this.local.getAudioTracks().forEach((t) => { t.enabled = this.audioOn })
        this.local.getVideoTracks().forEach((t) => { t.enabled = this.videoOn })
    }

    async devices() {
        try {
            const list = await navigator.mediaDevices.enumerateDevices()
            this.emit({
                type: 'devices',
                devices: list.map((d) => ({ id: d.deviceId, kind: d.kind, label: d.label })),
                mic: this.trackDevice('audio'), camera: this.trackDevice('video'),
            })
        } catch (e) {}
    }

    trackDevice(kind) {
        const track = this.local && (kind === 'audio' ? this.local.getAudioTracks() : this.local.getVideoTracks())[0]
        return track ? (track.getSettings().deviceId || '') : ''
    }

    // another microphone or camera, in the middle of a call: the new track replaces the old one in the publisher
    async switchDevice(kind, deviceId) {
        const constraints = kind === 'audio'
            ? { audio: { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true } }
            : { video: { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } } }
        let stream
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints)
        } catch (e) {
            this.emit({ type: 'error', code: 'device' })
            return
        }
        const track = stream.getTracks()[0]
        const old = kind === 'audio' ? this.local.getAudioTracks()[0] : this.local.getVideoTracks()[0]
        const blurred = kind === 'video' && Blur.active
        const raw = blurred ? Blur.stop(this, true) : old
        if (raw) {
            if (!blurred) this.local.removeTrack(raw)
            raw.stop()
        }
        this.local.addTrack(track)
        this.applyMute()
        if (this.publisher) {
            const sender = this.publisher.pc.getSenders().find((s) => s.track && s.track.kind === track.kind)
            if (sender) await sender.replaceTrack(track)
            else this.publish(true)
        }
        if (kind === 'audio') this.watchLevel()
        if (blurred) await Blur.set(this, 'blur', this.config.vision)
        this.devices()
        this.render()
    }

    async setOutput(deviceId) {
        this.outputId = deviceId
        document.querySelectorAll('video, audio').forEach((el) => {
            if (el.setSinkId) el.setSinkId(deviceId).catch(() => {})
        })
    }

    // speaking: the level of our microphone, told to the others like Talk does (data channel "status")
    watchLevel() {
        if (this.levelTimer) clearInterval(this.levelTimer)
        if (this.audioContext) this.audioContext.close().catch(() => {})   // one at a time (a microphone change)
        this.audioContext = null
        if (!this.hasAudio()) return
        const context = this.audioContext = new AudioContext()
        const analyser = context.createAnalyser()
        analyser.fftSize = 512
        context.createMediaStreamSource(new MediaStream(this.local.getAudioTracks())).connect(analyser)
        const data = new Uint8Array(analyser.fftSize)
        let loud = 0, quiet = 0
        this.levelTimer = setInterval(() => {
            analyser.getByteTimeDomainData(data)
            let sum = 0
            for (let i = 0; i < data.length; i++) {
                const v = (data[i] - 128) / 128
                sum += v * v
            }
            const level = Math.sqrt(sum / data.length)
            this.level = level
            // before the call, the meter of « Prêt à rejoindre ? »
            if (!this.signaling && (this.tick = (this.tick || 0) + 1) % 2 === 0) this.emit({ type: 'level', level: Math.min(1, level * 6) })
            if (!this.audioOn) {
                if (level > 0.05) this.emit({ type: 'speakingWhileMuted' })
                return
            }
            if (level > 0.03) { loud++; quiet = 0 } else { quiet++; loud = 0 }
            if (!this.speaking && loud >= 2) this.setSpeaking(true)
            else if (this.speaking && quiet >= 10) this.setSpeaking(false)
        }, 100)
    }

    setSpeaking(on) {
        this.speaking = on
        this.status(on ? 'speaking' : 'stoppedSpeaking')
        this.render()
    }

    // ---- what we send ----------------------------------------------------------------------------------------
    async publish(again) {
        if (!this.inCall || !this.signaling.sessionId) return
        if (this.publisher && !again) return
        this.stopPublisher('publisher')
        if (!this.hasAudio() && !this.hasVideo()) return
        const own = this.signaling.sessionId
        const pc = new RTCPeerConnection({ iceServers: this.ice, bundlePolicy: 'max-bundle' })
        const sid = String(Date.now())
        const dc = pc.createDataChannel('status')
        const pub = { pc, dc, sid, roomType: 'video', session: own }
        this.publisher = pub
        this.local.getAudioTracks().forEach((t) => pc.addTransceiver(t, { direction: 'sendonly', streams: [this.local] }))
        this.local.getVideoTracks().forEach((t) => pc.addTransceiver(t, {
            direction: 'sendonly', streams: [this.local],
            sendEncodings: this.signaling.hasFeature('simulcast') ? [
                { rid: 'h', active: true, maxBitrate: 900000 },
                { rid: 'l', active: true, maxBitrate: 100000, scaleResolutionDownBy: 4 },
            ] : undefined,
        }))
        dc.onopen = () => this.sendState()
        this.watchIce(pub, own)
        pc.onicecandidate = (e) => {
            if (e.candidate) this.signaling.sendTo(own, this.candidate(own, 'video', sid, e.candidate))
        }
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        this.signaling.sendTo(own, {
            to: own, type: 'offer', roomType: 'video', sid,
            payload: { type: 'offer', sdp: offer.sdp, nick: this.nick },
        })
        // no answer from the SFU: offer again (a new peer each time, an offer cannot be resent)
        pub.retry = setTimeout(() => {
            if (this.publisher === pub && pc.connectionState !== 'connected') this.publish(true)
        }, RETRY_MS)
    }

    stopPublisher(key) {
        const pub = this[key]
        if (!pub) return
        clearTimeout(pub.retry)
        try { pub.pc.close() } catch (e) {}
        this[key] = null
    }

    candidate(to, roomType, sid, c) {
        return {
            to, type: 'candidate', roomType, sid,
            payload: { candidate: { candidate: c.candidate, sdpMLineIndex: c.sdpMLineIndex, sdpMid: c.sdpMid } },
        }
    }

    // a small state for everyone: through the data channel (fast) and through the signaling (sure), like Talk
    status(type, payload) {
        if (this.publisher && this.publisher.dc.readyState === 'open') {
            this.publisher.dc.send(JSON.stringify({ type, payload }))
        }
    }

    toAll(type, payload) {
        if (!this.signaling) return
        this.users.forEach((user, session) => {
            if (user.inCall && session !== this.signaling.sessionId) {
                this.signaling.sendTo(session, { to: session, roomType: 'video', type, payload })
            }
        })
    }

    sendState(to) {
        const send = to
            ? (type, payload) => this.signaling.sendTo(to, { to, roomType: 'video', type, payload })
            : (type, payload) => this.toAll(type, payload)
        this.status(this.audioOn ? 'audioOn' : 'audioOff')
        this.status(this.videoOn ? 'videoOn' : 'videoOff')
        this.status('nickChanged', { name: this.nick, userid: this.config.userId })
        send(this.audioOn ? 'unmute' : 'mute', { name: 'audio' })
        send(this.videoOn ? 'unmute' : 'mute', { name: 'video' })
        send('nickChanged', { name: this.nick })
        if (this.hand) send('raiseHand', { state: true, timestamp: this.handAt })
    }

    setAudio(on) {
        this.audioOn = on && this.hasAudio()
        this.applyMute()
        if (!this.audioOn && this.speaking) this.setSpeaking(false)
        this.status(this.audioOn ? 'audioOn' : 'audioOff')
        this.toAll(this.audioOn ? 'unmute' : 'mute', { name: 'audio' })
        this.render()
    }

    setVideo(on) {
        this.videoOn = on && this.hasVideo()
        this.applyMute()
        this.status(this.videoOn ? 'videoOn' : 'videoOff')
        this.toAll(this.videoOn ? 'unmute' : 'mute', { name: 'video' })
        this.render()
    }

    setHand(on) {
        this.hand = on
        this.handAt = Date.now()
        this.toAll('raiseHand', { state: on, timestamp: this.handAt })
        this.render()
    }

    react(emoji) {
        if (!this.signaling) return
        this.toAll('reaction', { reaction: emoji })
        this.view.reaction(this.signaling.sessionId, emoji)
        this.emit({ type: 'reaction', session: this.signaling.sessionId, reaction: emoji, self: true })
    }

    // ---- screen share ----------------------------------------------------------------------------------------
    async shareScreen(on) {
        if (!this.signaling) return
        if (!on) {
            this.stopScreen()
            return
        }
        if (this.screen || this.pickingScreen) return     // already shared, or the system is asking
        this.pickingScreen = true
        try {
            this.screen = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 15 } }, audio: false })
        } catch (e) {
            this.emit({ type: 'screen', on: false, cancelled: true })
            return
        } finally {
            this.pickingScreen = false
        }
        if (this.left) {
            this.screen.getTracks().forEach((t) => t.stop())
            this.screen = null
            return
        }
        this.screen.getVideoTracks()[0].onended = () => this.stopScreen()
        const own = this.signaling.sessionId
        const pc = new RTCPeerConnection({ iceServers: this.ice, bundlePolicy: 'max-bundle' })
        const sid = String(Date.now())
        const pub = { pc, sid, roomType: 'screen', session: own }
        this.screenPublisher = pub
        this.screen.getVideoTracks().forEach((t) => pc.addTransceiver(t, { direction: 'sendonly', streams: [this.screen] }))
        pc.onicecandidate = (e) => {
            if (e.candidate) this.signaling.sendTo(own, this.candidate(own, 'screen', sid, e.candidate))
        }
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        this.signaling.sendTo(own, {
            to: own, type: 'offer', roomType: 'screen', sid,
            payload: { type: 'offer', sdp: offer.sdp, nick: this.nick },
        })
        this.emit({ type: 'screen', on: true })
        this.render()
    }

    // the others cannot know a screen is shared: we ask the SFU to send them its offer (Talk does the same)
    offerScreenTo(session) {
        if (this.screenPublisher && session !== this.signaling.sessionId) this.signaling.sendOffer(session, 'screen')
    }

    stopScreen() {
        if (!this.screen) return
        this.screen.getTracks().forEach((t) => t.stop())
        this.screen = null
        this.toAll('unshareScreen', {})
        this.stopPublisher('screenPublisher')
        this.emit({ type: 'screen', on: false })
        this.render()
    }

    // ---- what we receive -------------------------------------------------------------------------------------
    subscribe(session, user) {
        if (!this.inCall || session === this.signaling.sessionId) return
        if (!(user.inCall & (WITH_AUDIO | WITH_VIDEO))) return
        if (this.peers.has(session + '|video') || this.retries.has(session)) return
        this.signaling.requestOffer(session, 'video')
        this.retries.set(session, setInterval(() => {
            if (this.peers.has(session + '|video')) {
                clearInterval(this.retries.get(session))
                this.retries.delete(session)
            } else {
                this.signaling.requestOffer(session, 'video')
            }
        }, RETRY_MS))
    }

    async onOffer(message) {
        const from = message.from
        const roomType = message.roomType || 'video'
        const key = from + '|' + roomType
        const old = this.peers.get(key)
        if (old) {
            if (old.sid === message.sid && old.pc.signalingState !== 'closed') {
                // a renegotiation of the same peer (the publisher added or removed a track)
                await old.pc.setRemoteDescription(message.payload)
                const answer = await old.pc.createAnswer()
                await old.pc.setLocalDescription(answer)
                this.answer(from, roomType, message.sid, answer)
                return
            }
            this.closePeer(old)
        }
        const pc = new RTCPeerConnection({ iceServers: this.ice, bundlePolicy: 'max-bundle' })
        const peer = { pc, sid: message.sid, session: from, roomType, stream: new MediaStream(), dc: null }
        this.peers.set(key, peer)
        if (this.retries.has(from) && roomType === 'video') {
            clearInterval(this.retries.get(from))
            this.retries.delete(from)
        }
        pc.ontrack = (e) => {
            peer.stream.addTrack(e.track)
            e.track.onunmute = () => this.render()
            this.render()
        }
        pc.ondatachannel = (e) => {
            peer.dc = e.channel
            e.channel.onmessage = (m) => {
                try {
                    const data = JSON.parse(m.data)
                    this.onStatus(from, data.type, data.payload)
                } catch (err) {}
            }
        }
        pc.onicecandidate = (e) => {
            if (e.candidate) this.signaling.sendTo(from, this.candidate(from, roomType, message.sid, e.candidate))
        }
        this.watchIce(peer, from)
        await pc.setRemoteDescription(message.payload)
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        this.answer(from, roomType, message.sid, answer)
        this.render()
    }

    answer(to, roomType, sid, answer) {
        this.signaling.sendTo(to, {
            to, type: 'answer', roomType, sid,
            payload: { type: 'answer', sdp: answer.sdp, nick: this.nick },
        })
    }

    // a peer that fails is made again: we offer again (ours) or ask for a new offer (theirs)
    watchIce(peer, session) {
        // DTLS ends after ICE: "published" (connectionState) needs its own event
        peer.pc.onconnectionstatechange = () => this.render()
        peer.pc.oniceconnectionstatechange = () => {
            const state = peer.pc.iceConnectionState
            peer.state = state
            if (state === 'failed') {
                if (peer === this.publisher) this.publish(true)
                else if (peer === this.screenPublisher) { this.stopScreen(); this.emit({ type: 'error', code: 'screen_failed' }) }
                else {
                    this.closePeer(peer)
                    this.peers.delete(peer.session + '|' + peer.roomType)
                    const user = this.users.get(session)
                    if (user && peer.roomType === 'video') this.subscribe(session, user)
                }
            }
            this.render()
        }
    }

    closePeer(peer) {
        try { peer.pc.close() } catch (e) {}
        peer.stream.getTracks().forEach((t) => t.stop())
    }

    onMessage(message) {
        const from = message.from
        const own = this.signaling.sessionId
        switch (message.type) {
        case 'offer':
            this.onOffer(message)
            break
        case 'answer': {
            const pub = message.roomType === 'screen' ? this.screenPublisher : this.publisher
            if (pub && from === own && (!message.sid || message.sid === pub.sid)) {
                clearTimeout(pub.retry)
                pub.pc.setRemoteDescription(message.payload).catch(() => {})
                // the SFU has our screen: everyone already in the call gets its offer
                if (pub === this.screenPublisher) this.users.forEach((user, session) => { if (user.inCall) this.offerScreenTo(session) })
            }
            break
        }
        case 'candidate': {
            const target = from === own
                ? (message.roomType === 'screen' ? this.screenPublisher : this.publisher)
                : this.peers.get(from + '|' + (message.roomType || 'video'))
            const c = message.payload && message.payload.candidate
            if (target && c) target.pc.addIceCandidate(c).catch(() => {})
            break
        }
        case 'unshareScreen': {
            const peer = this.peers.get(from + '|screen')
            if (peer) {
                this.closePeer(peer)
                this.peers.delete(from + '|screen')
                this.render()
            }
            break
        }
        case 'mute':
        case 'unmute': {
            const on = message.type === 'unmute'
            const name = message.payload && message.payload.name
            if (name === 'audio') this.patch(from, { audio: on, speaking: on ? undefined : false })
            if (name === 'video') this.patch(from, { video: on })
            break
        }
        case 'nickChanged':
            this.patch(from, { name: (message.payload && message.payload.name) || '' })
            break
        case 'raiseHand':
            this.patch(from, { hand: !!(message.payload && message.payload.state) })
            if (message.payload && message.payload.state) this.emit({ type: 'hand', session: from, name: this.nameOf(from) })
            break
        case 'reaction':
            if (message.payload && message.payload.reaction) {
                this.view.reaction(from, message.payload.reaction)
                this.emit({ type: 'reaction', session: from, name: this.nameOf(from), reaction: message.payload.reaction })
            }
            break
        case 'control':
            // a moderator muted us ("forceMute"), like Talk
            if (message.payload && message.payload.action === 'forceMute' && message.payload.peerId === own) {
                this.setAudio(false)
                this.emit({ type: 'forcedMute' })
            }
            break
        }
    }

    onStatus(from, type, payload) {
        switch (type) {
        case 'audioOn': this.patch(from, { audio: true }); break
        case 'audioOff': this.patch(from, { audio: false, speaking: false }); break
        case 'videoOn': this.patch(from, { video: true }); break
        case 'videoOff': this.patch(from, { video: false }); break
        case 'speaking': this.patch(from, { speaking: true }); break
        case 'stoppedSpeaking': this.patch(from, { speaking: false }); break
        case 'nickChanged': {
            const name = typeof payload === 'string' ? payload : (payload && payload.name) || ''
            this.patch(from, { name })
            break
        }
        }
    }

    // ---- who is there ----------------------------------------------------------------------------------------
    onEvent(event) {
        if (event.target === 'self' && event.type === 'joined') {
            this.reconnecting = false
            if (this.inCall) {
                // back after a cut long enough for a new session: what we sent and received went with the old
                // one. Python joins the call again (POST /call), then « inCall » publishes and subscribes anew.
                this.inCall = false
                this.retries.forEach((timer) => clearInterval(timer))
                this.retries.clear()
                this.peers.forEach((peer) => this.closePeer(peer))
                this.peers.clear()
                this.stopPublisher('publisher')
                this.stopScreen()                 // shared again by hand: the system asks which screen anyway
                this.render()
                this.emit({ type: 'rejoined', session: this.signaling.sessionId })
                return
            }
            this.emit({ type: 'roomJoined', session: this.signaling.sessionId, features: [...this.signaling.features] })
            return
        }
        if (event.target === 'room') {
            if (event.type === 'join') {
                ;(event.join || []).forEach((j) => {
                    const user = this.users.get(j.sessionid) || { inCall: 0 }
                    user.userId = j.userid || user.userId || ''
                    const name = (j.user && (j.user.displayname || j.user.displayName)) || this.people[user.userId]
                    if (name && !user.name) user.name = name
                    this.users.set(j.sessionid, user)
                })
                this.render()
            } else if (event.type === 'leave') {
                ;(event.leave || []).forEach((session) => this.gone(session))
                this.render()
            } else if (event.type === 'message' && event.message && event.message.data) {
                this.emit({ type: 'roomMessage', data: event.message.data })
            } else if (event.type === 'switchto') {
                this.emit({ type: 'switchto', token: event.switchto && event.switchto.roomid })
            }
            return
        }
        if (event.target === 'participants') {
            if (event.type === 'update' && event.update) {
                if (event.update.all && event.update.incall === 0) {
                    // the call was ended for everyone
                    this.emit({ type: 'ended' })
                    return
                }
                ;(event.update.users || []).forEach((u) => this.updateUser(u))
                this.render()
            }
            return
        }
        if (event.target === 'roomlist') {
            this.emit({ type: 'roomlist', event })
        }
    }

    updateUser(u) {
        const session = u.sessionId || u.sessionid
        if (!session) return
        const own = this.signaling.sessionId
        const user = this.users.get(session) || {}
        const wasIn = user.inCall || 0
        user.inCall = u.inCall || 0
        user.userId = u.userId || u.userid || user.userId || ''
        user.actorType = u.actorType || user.actorType
        user.actorId = u.actorId || user.actorId
        user.nextcloudSessionId = u.nextcloudSessionId || user.nextcloudSessionId
        user.participantType = u.participantType || user.participantType
        if (!user.name) user.name = (u.displayName || u.displayname) || this.people[user.userId] || ''
        if (user.audio === undefined) user.audio = !!(user.inCall & WITH_AUDIO)
        if (user.video === undefined) user.video = !!(user.inCall & WITH_VIDEO)
        this.users.set(session, user)
        if (session === own) return
        if (user.inCall && !wasIn) {
            this.emit({ type: 'joinedCall', session, name: this.nameOf(session) })
            this.subscribe(session, user)
            this.offerScreenTo(session)
            if (this.inCall) this.sendState(session)
        } else if (user.inCall && (user.inCall & (WITH_AUDIO | WITH_VIDEO)) !== (wasIn & (WITH_AUDIO | WITH_VIDEO))) {
            this.subscribe(session, user)
        } else if (!user.inCall && wasIn) {
            this.emit({ type: 'leftCall', session, name: this.nameOf(session) })
            this.dropPeers(session)
        }
    }

    gone(session) {
        this.dropPeers(session)
        this.users.delete(session)
    }

    dropPeers(session) {
        ;['video', 'screen'].forEach((roomType) => {
            const peer = this.peers.get(session + '|' + roomType)
            if (peer) {
                this.closePeer(peer)
                this.peers.delete(session + '|' + roomType)
            }
        })
        if (this.retries.has(session)) {
            clearInterval(this.retries.get(session))
            this.retries.delete(session)
        }
    }

    patch(session, values) {
        const user = this.users.get(session) || { inCall: 0 }
        Object.keys(values).forEach((k) => { if (values[k] !== undefined) user[k] = values[k] })
        this.users.set(session, user)
        this.render()
    }

    nameOf(session) {
        const user = this.users.get(session)
        return (user && (user.name || this.people[user.userId])) || ''
    }

    // ---- what QML and the grid see ---------------------------------------------------------------------------
    // batched in a microtask, not requestAnimationFrame: that one stops while the window is hidden or minimised
    render() {
        if (this.renderQueued) return
        this.renderQueued = true
        Promise.resolve().then(() => {
            this.renderQueued = false
            this.view.update()
            this.emit({ type: 'state', state: this.snapshot() })
        })
    }

    snapshot() {
        const own = this.signaling ? this.signaling.sessionId : ''
        const people = []
        this.users.forEach((user, session) => {
            if (session === own || !user.inCall) return
            const peer = this.peers.get(session + '|video')
            people.push({
                session, userId: user.userId || '', name: user.name || this.people[user.userId] || '',
                audio: !!user.audio, video: !!user.video, speaking: !!user.speaking, hand: !!user.hand,
                screen: this.peers.has(session + '|screen'),
                connection: peer ? (peer.state || 'new') : ((user.inCall & (WITH_AUDIO | WITH_VIDEO)) ? 'waiting' : 'none'),
                actorType: user.actorType || '', actorId: user.actorId || '',
            })
        })
        return {
            session: own, inCall: this.inCall, audio: this.audioOn, video: this.videoOn,
            hasAudio: this.hasAudio(), hasVideo: this.hasVideo(), speaking: this.speaking, hand: this.hand,
            screen: !!this.screen, published: !!(this.publisher && this.publisher.pc.connectionState === 'connected'),
            preview: !this.signaling, blur: !!Blur.active, reconnecting: !!this.reconnecting,
            people,
        }
    }

    // ---- what Python asks ------------------------------------------------------------------------------------
    command(data) {
        switch (data.cmd) {
        case 'inCall': this.enterCall(); break
        case 'audio': this.setAudio(!!data.on); break
        case 'video': this.setVideo(!!data.on); break
        case 'screen': this.shareScreen(!!data.on); break
        case 'hand': this.setHand(!!data.on); break
        case 'reaction': this.react(data.reaction); break
        case 'leave': this.leave(); break
        case 'devices': this.devices(); break
        case 'mic': this.switchDevice('audio', data.id); break
        case 'camera': this.switchDevice('video', data.id); break
        case 'speaker': this.setOutput(data.id); break
        case 'layout': this.view.setLayout(data.layout); break
        case 'pin': this.view.pin(data.session || ''); break
        case 'people': Object.assign(this.people, data.people || {}); this.render(); break
        case 'theme': document.documentElement.dataset.theme = data.theme; break
        case 'muteOther':
            // moderators: mute someone, like Talk's "forceMute"
            this.signaling.control(data.session, { action: 'forceMute', peerId: data.session })
            break
        case 'blur':
            if (data.vision) this.config.vision = data.vision
            Blur.set(this, data.on ? 'blur' : '', this.config.vision)
            break
        case 'connect': this.connect(data); break
        case 'rejoin':
            // the conversation's session was gone (a long cut): the new one Python got, the room again
            if (data.ncSession) this.config.ncSession = data.ncSession
            if (this.signaling) this.signaling.joinRoom(this.config.token, this.config.ncSession)
            break
        case 'stats': this.stats(); break
        }
    }

    // the quality of the call: bytes and packets lost for what we receive and send, the round trip to the SFU
    async stats() {
        const out = { inbound: { audio: 0, video: 0 }, lost: 0, received: 0, outbound: { audio: 0, video: 0 }, rtt: 0 }
        const read = async (pc, inbound) => {
            const report = await pc.getStats()
            report.forEach((s) => {
                if (inbound && s.type === 'inbound-rtp') {
                    out.inbound[s.kind] += s.bytesReceived || 0
                    out.lost += s.packetsLost || 0
                    out.received += s.packetsReceived || 0
                } else if (!inbound && s.type === 'outbound-rtp') {
                    out.outbound[s.kind] += s.bytesSent || 0
                } else if (!inbound && s.type === 'candidate-pair' && s.nominated && s.currentRoundTripTime) {
                    out.rtt = Math.round(s.currentRoundTripTime * 1000)
                }
            })
        }
        try {
            for (const peer of this.peers.values()) await read(peer.pc, true)
            if (this.publisher) await read(this.publisher.pc, false)
        } catch (e) {}
        // ours: the size of what the camera gives, and the frames the blur drew
        const own = this.local && this.local.getVideoTracks()[0]
        out.self = own ? own.getSettings() : null
        out.blurFrames = Blur.active ? Blur.active.frames : -1
        out.blurCost = Blur.active ? Math.round(Blur.active.cost || 0) : 0
        this.emit({ type: 'stats', stats: out })
    }
}

window.Call = Call

// the page starts when QWebChannel gives the bridge
window.addEventListener('load', () => {
    if (!window.qt || !window.QWebChannel) return
    new QWebChannel(qt.webChannelTransport, (channel) => {
        const bridge = channel.objects.bridge
        const config = JSON.parse(bridge.config)
        document.documentElement.dataset.theme = config.theme || 'light'
        if (config.labels) Grid.labels = config.labels
        const call = new Call(bridge, config)
        window.call = call
        bridge.command.connect((json) => call.command(JSON.parse(json)))
        // after the connection above: the channel handles messages in order, so no command is lost
        bridge.event(JSON.stringify({ type: 'loaded' }))
        call.start()
    })
})
