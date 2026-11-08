// The signaling of a call: the WebSocket to the cloud's high-performance backend (signaling.orneos.eu, the
// "standalone signaling" of Nextcloud Talk). Protocol: docs/standalone-signaling-api-v1.md of
// strukturag/nextcloud-spreed-signaling, as Talk's own signaling.js speaks it (hello v2, room, message, control).
//
// It only carries messages: who is in the room and in the call, and the offers / answers / candidates between
// our peers and the SFU (Janus). The Nextcloud side (entering the conversation, joining the call) is done by
// Python before and after (meet_core/call.py), which hands the Nextcloud session id over.
'use strict'

class Signaling {
    constructor(settings, handlers) {
        this.settings = settings          // GET /api/v3/signaling/settings
        this.on = handlers                // {event(data), message(data), connected(), lost(), error(code)}
        this.sessionId = ''               // ours, on the signaling server (what peers call "from" / "to")
        this.resumeId = ''
        this.features = new Set()
        this.socket = null
        this.nextId = 1
        this.callbacks = {}
        this.pending = []
        this.connected = false
        this.closed = false
        this.room = null                  // {token, ncSession}
        this.retryMs = 1000
        let url = (Array.isArray(settings.server) ? settings.server[0] : settings.server) || ''
        url = url.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://').replace(/\/$/, '')
        this.url = url + '/spreed'
    }

    hasFeature(name) {
        return this.features.has(name)
    }

    connect() {
        if (this.closed) return
        this.socket = new WebSocket(this.url)
        this.socket.onopen = () => {
            this.retryMs = 1000
            this.hello()
        }
        this.socket.onmessage = (event) => this.receive(JSON.parse(event.data))
        this.socket.onclose = () => {
            const was = this.connected
            this.connected = false
            this.socket = null
            if (this.closed) return
            if (was && this.on.lost) this.on.lost()
            setTimeout(() => this.connect(), this.retryMs)
            this.retryMs = Math.min(this.retryMs * 2, 16000)
        }
        this.socket.onerror = () => {}
    }

    close() {
        this.closed = true
        if (this.socket) {
            try { this.send({ type: 'bye', bye: {} }) } catch (e) {}
            this.socket.close()
        }
    }

    send(msg, callback) {
        if ((!this.connected && msg.type !== 'hello') || !this.socket || this.socket.readyState !== 1) {
            if (msg.type !== 'hello' && msg.type !== 'bye') this.pending.push([msg, callback])
            return
        }
        if (callback) {
            const id = String(this.nextId++)
            this.callbacks[id] = callback
            msg.id = id
        }
        this.socket.send(JSON.stringify(msg))
    }

    hello() {
        if (this.resumeId) {
            this.send({ type: 'hello', hello: { version: '1.0', resumeid: this.resumeId } }, (r) => this.helloAnswer(r))
            return
        }
        const params = this.settings.helloAuthParams || {}
        const version = params['2.0'] ? '2.0' : '1.0'
        const backend = this.settings.backend
        this.send({
            type: 'hello',
            hello: { version, features: ['chat-relay'], auth: { url: backend, params: params[version] } },
        }, (r) => this.helloAnswer(r))
    }

    helloAnswer(data) {
        if (data.type !== 'hello') {
            if (this.resumeId) {           // the old session is gone: a new one
                this.resumeId = ''
                this.hello()
                return
            }
            // refused (an expired ticket): no endless retry, the call ends and says so (call.py)
            this.closed = true
            if (this.on.error) this.on.error((data.error && data.error.code) || 'hello_failed')
            if (this.socket) this.socket.close()
            return
        }
        const resumed = !!this.resumeId
        this.connected = true
        this.sessionId = data.hello.sessionid
        this.resumeId = data.hello.resumeid
        this.features = new Set((data.hello.server && data.hello.server.features) || [])
        const pending = this.pending
        this.pending = []
        pending.forEach(([msg, cb]) => this.send(msg, cb))
        if (this.on.connected) this.on.connected(resumed)
        if (!resumed && this.room) this.joinRoom(this.room.token, this.room.ncSession)
    }

    joinRoom(token, ncSession) {
        this.room = { token, ncSession }
        if (!this.connected) return
        this.send({ type: 'room', room: { roomid: token, sessionid: ncSession } }, (data) => {
            if (data.type === 'error') {
                // 'room': the conversation's session was refused (a new one can be asked: call.py)
                if (this.on.error) this.on.error(data.error.code, 'room')
                return
            }
            if (this.on.event) this.on.event({ target: 'self', type: 'joined', room: data.room })
        })
    }

    leaveRoom() {
        this.room = null
        if (this.connected) this.send({ type: 'room', room: { roomid: '', sessionid: '' } })
    }

    // to one session (an offer, an answer, a candidate, a state for one participant)
    sendTo(sessionId, data) {
        this.send({ type: 'message', message: { recipient: { type: 'session', sessionid: sessionId }, data } })
    }

    // to the whole room
    sendToRoom(data) {
        this.send({ type: 'message', message: { recipient: { type: 'room' }, data } })
    }

    control(sessionId, data) {
        this.send({ type: 'control', control: { recipient: { type: 'session', sessionid: sessionId }, data } })
    }

    requestOffer(sessionId, roomType) {
        this.sendTo(sessionId, { type: 'requestoffer', roomType })
    }

    sendOffer(sessionId, roomType) {
        this.sendTo(sessionId, { type: 'sendoffer', roomType })
    }

    receive(data) {
        const id = data.id
        if (id && this.callbacks[id]) {
            const cb = this.callbacks[id]
            delete this.callbacks[id]
            cb(data)
            if (data.type === 'hello' || data.type === 'room') return
        }
        switch (data.type) {
        case 'hello':
            if (!id) this.helloAnswer(data)
            break
        case 'event':
            if (this.on.event) this.on.event(data.event)
            break
        case 'message':
            data.message.data.from = data.message.sender.sessionid
            if (this.on.message) this.on.message(data.message.data)
            break
        case 'control':
            if (this.on.message) {
                this.on.message({ type: 'control', payload: data.control.data, from: data.control.sender.sessionid })
            }
            break
        case 'error':
            // only what ends the call: a message to someone who just left (no_such_session…) is not
            if (data.error.code === 'token_expired' || data.error.code === 'no_such_room') {
                if (this.on.error) this.on.error(data.error.code)
            }
            break
        }
    }
}

window.Signaling = Signaling
