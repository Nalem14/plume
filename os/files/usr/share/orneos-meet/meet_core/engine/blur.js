// The background blur of our camera, like Talk's: MediaPipe's selfie segmenter finds the person in each frame,
// the rest is drawn blurred on a canvas, and the canvas's track takes the camera's place everywhere (our tile,
// what we publish). Its wasm and model are files of the cache (meet_core/vision.py): fetch() cannot read
// file://, so they are read by XHR and handed to MediaPipe as blob: URLs. The frames are paced by a worker
// (a page's timers slow down to one a second when the window is hidden, a worker's do not), each one asked
// once the last is drawn: about 30 a second, fewer on a slow computer, without ever piling up.
'use strict'

const Blur = {
    segmenter: null,
    loading: null,
    active: null,         // {raw, out, video, canvas, ticker}

    read(path) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest()
            xhr.open('GET', 'file://' + path)
            xhr.responseType = 'arraybuffer'
            xhr.onload = () => (xhr.response && xhr.response.byteLength ? resolve(xhr.response) : reject(new Error('empty')))
            xhr.onerror = () => reject(new Error('xhr'))
            xhr.send()
        })
    },

    load(assets) {
        if (this.segmenter) return Promise.resolve(this.segmenter)
        if (!this.loading) {
            this.loading = (async () => {
                const [loader, wasm, model] = await Promise.all([this.read(assets.loader), this.read(assets.wasm), this.read(assets.model)])
                const fileset = {
                    wasmLoaderPath: URL.createObjectURL(new Blob([loader], { type: 'text/javascript' })),
                    wasmBinaryPath: URL.createObjectURL(new Blob([wasm], { type: 'application/wasm' })),
                }
                const make = (delegate) => MPVision.ImageSegmenter.createFromOptions(fileset, {
                    baseOptions: { modelAssetBuffer: new Uint8Array(model), delegate },
                    runningMode: 'VIDEO', outputCategoryMask: false, outputConfidenceMasks: true,
                })
                try {
                    this.segmenter = await make('GPU')
                } catch (e) {
                    this.segmenter = await make('CPU')
                }
                return this.segmenter
            })()
            this.loading.catch(() => { this.loading = null })
        }
        return this.loading
    },

    async set(call, mode, assets) {
        if (!mode) {
            this.stop(call)
            return
        }
        if (this.active) return
        const raw = call.local && call.local.getVideoTracks()[0]
        if (!raw || !assets) return
        let seg
        try {
            seg = await this.load(assets)
        } catch (e) {
            const detail = String((e && (e.message || e)) || '').split('\n')[0].slice(0, 300)
            console.error('blur: ' + detail)
            call.emit({ type: 'error', code: 'blur', detail })
            return
        }
        if (this.active || call.left || !call.local || call.local.getVideoTracks()[0] !== raw) return
        const settings = raw.getSettings()
        const scale = Math.min(1, 960 / (settings.width || 960))
        const W = Math.round((settings.width || 960) * scale), H = Math.round((settings.height || 540) * scale)
        const video = document.createElement('video')
        video.muted = true
        video.playsInline = true
        video.srcObject = new MediaStream([raw])
        video.play().catch(() => {})
        const canvas = document.createElement('canvas')
        canvas.width = W; canvas.height = H
        const ctx = canvas.getContext('2d')
        const person = document.createElement('canvas')
        person.width = W; person.height = H
        const pctx = person.getContext('2d')
        const maskCanvas = document.createElement('canvas')
        const mctx = maskCanvas.getContext('2d')
        let image = null
        const frame = () => {
            if (video.readyState < 2 || !call.videoOn) return
            if (this.active) this.active.frames++
            let result
            try {
                result = seg.segmentForVideo(video, performance.now())
            } catch (e) {
                return
            }
            const masks = (result && result.confidenceMasks) || []
            const mask = masks[masks.length > 1 ? 1 : 0]
            if (mask) {
                if (maskCanvas.width !== mask.width || maskCanvas.height !== mask.height || !image) {
                    maskCanvas.width = mask.width; maskCanvas.height = mask.height
                    image = mctx.createImageData(mask.width, mask.height)
                }
                const conf = mask.getAsFloat32Array()
                const px = image.data
                for (let i = 0; i < conf.length; i++) px[i * 4 + 3] = conf[i] * 255
                mctx.putImageData(image, 0, 0)
            }
            if (result && result.close) result.close()
            ctx.globalCompositeOperation = 'copy'
            ctx.filter = 'blur(16px)'
            ctx.drawImage(video, -24, -24, W + 48, H + 48)
            ctx.filter = 'none'
            pctx.globalCompositeOperation = 'copy'
            pctx.filter = 'blur(2px)'                 // soft edges around the person
            pctx.drawImage(maskCanvas, 0, 0, W, H)
            pctx.filter = 'none'
            pctx.globalCompositeOperation = 'source-in'
            pctx.drawImage(video, 0, 0, W, H)
            ctx.globalCompositeOperation = 'source-over'
            ctx.drawImage(person, 0, 0)
        }
        // one frame, then the next one asked: a slow computer gets fewer frames, never a queue of them
        const ticker = new Worker(URL.createObjectURL(new Blob(['onmessage = (e) => setTimeout(() => postMessage(0), e.data)'],
                                                               { type: 'text/javascript' })))
        ticker.onmessage = () => {
            const begin = performance.now()
            try { frame() } catch (e) {}
            const cost = performance.now() - begin
            const a = this.active
            if (!a || a.ticker !== ticker) return
            a.cost = cost
            // too slow for this computer (no graphics acceleration: a virtual machine): the camera as it is
            if (a.frames >= 3 && cost > 250) {
                this.stop(call)
                call.emit({ type: 'error', code: 'blur_slow' })
                return
            }
            ticker.postMessage(Math.max(33 - cost, cost, 4))
        }
        ticker.postMessage(0)
        const out = canvas.captureStream(30).getVideoTracks()[0]
        out.enabled = raw.enabled
        this.active = { raw, out, video, ticker, frames: 0 }
        await this.swap(call, raw, out)
        call.emit({ type: 'blur', on: true })
    },

    // our tile and the publisher take `to` instead of `from` (the camera keeps running under the blur)
    async swap(call, from, to) {
        call.local.removeTrack(from)
        call.local.addTrack(to)
        if (call.publisher) {
            const sender = call.publisher.pc.getSenders().find((s) => s.track === from)
            if (sender) await sender.replaceTrack(to).catch(() => {})
        }
        const self = call.view.tiles.get('self')
        if (self) self.querySelector('video').srcObject = call.local
        call.render()
    },

    stop(call, keepRaw) {
        const a = this.active
        if (!a) return
        this.active = null
        a.ticker.terminate()
        a.video.srcObject = null
        if (call.local && call.local.getVideoTracks().indexOf(a.out) >= 0) {
            a.raw.enabled = a.out.enabled
            if (keepRaw) call.local.removeTrack(a.out)
            else this.swap(call, a.out, a.raw)
        }
        a.out.stop()
        call.emit({ type: 'blur', on: false })
        return a.raw
    },
}

window.Blur = Blur
