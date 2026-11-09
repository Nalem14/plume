// Ornis's hands in a page: what the agent reads (an accessibility snapshot with refs, like Playwright's) and what
// it does (click, type, choose, scroll), run in an isolated world of the page (its globals are not the page's, the
// page cannot reach it). Every function returns a JSON string. Passwords: a password field's value is never read
// back; the Trousseau fills fields through fill(), whose value never comes back either.
window.__oa = (function () {
    "use strict";
    let next = 1;
    const ids = new WeakMap();
    const els = new Map();
    const ROLE = { A: "link", BUTTON: "button", SELECT: "combobox", TEXTAREA: "textbox", SUMMARY: "button",
                   H1: "heading", H2: "heading", H3: "heading", H4: "heading", H5: "heading", H6: "heading",
                   IMG: "img", NAV: "navigation", MAIN: "main", DIALOG: "dialog", LI: "listitem", TABLE: "table",
                   FORM: "form", LABEL: "", OPTION: "option", IFRAME: "frame" };
    const INPUT = { checkbox: "checkbox", radio: "radio", button: "button", submit: "button", reset: "button",
                    range: "slider", search: "searchbox", file: "file", image: "button" };
    const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "HEAD", "META", "LINK"]);
    const TEXTUAL = new Set(["P", "SPAN", "DIV", "TD", "TH", "DD", "DT", "LI", "BLOCKQUOTE", "PRE", "CODE", "TIME",
                             "STRONG", "EM", "B", "I", "SMALL", "ARTICLE", "SECTION", "LABEL", "FIGCAPTION", "CAPTION"]);

    function ref(el) {
        let id = ids.get(el);
        if (!id || els.get(id) !== el) {
            id = "e" + (next++);
            ids.set(el, id);
            els.set(id, el);
        }
        return id;
    }
    function get(id) {
        const el = els.get(String(id || ""));
        if (!el || !el.isConnected) throw new Error("ref " + id + " is gone: take a new snapshot");
        return el;
    }
    function shown(el) {
        // CSS decides (display, visibility, opacity, content-visibility); a box of no size is hidden only when it
        // has nothing visible inside either (a wrapper of 0 px with overflowing content is common)
        if (!(el instanceof Element)) return false;
        if (typeof el.checkVisibility === "function"
            && !el.checkVisibility({ checkOpacity: el.tagName !== "INPUT", checkVisibilityCSS: true })) return false;
        const st = getComputedStyle(el);
        if (st.display === "none" || st.visibility === "hidden" || st.visibility === "collapse") return false;
        const r = el.getBoundingClientRect();
        if (r.width > 0 || r.height > 0 || st.display === "contents") return true;
        return el.children.length > 0 && st.overflow !== "hidden";
    }
    function clean(t, max) {
        t = String(t || "").replace(/\s+/g, " ").trim();
        return max && t.length > max ? t.slice(0, max - 1) + "…" : t;
    }
    function roleOf(el) {
        const aria = el.getAttribute("role");
        if (aria) return aria.split(" ")[0];
        if (el.tagName === "INPUT") return INPUT[(el.type || "text").toLowerCase()] || "textbox";
        if (el.isContentEditable && el.parentElement && !el.parentElement.isContentEditable) return "textbox";
        if (el.tagName === "A") return el.hasAttribute("href") ? "link" : "";
        return ROLE[el.tagName] || "";
    }
    function nameOf(el) {
        const by = el.getAttribute("aria-labelledby");
        if (by) {
            const t = by.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(n => n.innerText).join(" ");
            if (clean(t)) return clean(t, 120);
        }
        const aria = el.getAttribute("aria-label");
        if (aria) return clean(aria, 120);
        if (el.labels && el.labels.length) return clean(Array.from(el.labels).map(l => l.innerText).join(" "), 120);
        if (el.tagName === "IMG") return clean(el.alt || el.title, 120);
        if (el.tagName === "INPUT" && /^(submit|button|reset)$/i.test(el.type)) return clean(el.value, 120);
        const inner = el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" ? "" : el.innerText;
        return clean(inner || el.getAttribute("placeholder") || el.title || el.getAttribute("name") || "", 120);
    }
    function interactive(el) {
        if (el.disabled) return false;
        const role = roleOf(el);
        if (["link", "button", "textbox", "searchbox", "checkbox", "radio", "combobox", "slider", "switch", "tab",
             "menuitem", "option", "file", "listbox", "menuitemcheckbox", "treeitem"].includes(role)) return true;
        if (el.hasAttribute("onclick") || el.tabIndex >= 0 && el.tagName !== "DIV" && el.tagName !== "SPAN") return true;
        return getComputedStyle(el).cursor === "pointer" && !(el.parentElement && getComputedStyle(el.parentElement).cursor === "pointer");
    }
    function state(el) {
        const out = [];
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
            if (el.type === "password") out.push(el.value ? "filled" : "empty");
            else if (el.type === "checkbox" || el.type === "radio") out.push(el.checked ? "checked" : "unchecked");
            else if (el.value) out.push('value="' + clean(el.value, 80) + '"');
            if (el.type && el.type !== "text") out.push("type=" + el.type);
        } else if (el.tagName === "SELECT") {
            const o = el.options[el.selectedIndex];
            if (o) out.push('value="' + clean(o.text, 60) + '"');
        } else if (el.isContentEditable && el.innerText.trim()) {
            out.push('value="' + clean(el.innerText, 80) + '"');
        }
        if (el.getAttribute("aria-expanded")) out.push("expanded=" + el.getAttribute("aria-expanded"));
        if (el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-current")) out.push("selected");
        if (/^H[1-6]$/.test(el.tagName)) out.push("level=" + el.tagName[1]);
        if (el.tagName === "A" && el.getAttribute("href")) {
            const h = el.getAttribute("href");
            if (!h.startsWith("javascript:")) out.push("href=" + clean(h, 100));
        }
        return out;
    }

    function snapshot(rootRef, max) {
        max = max || 14000;
        const root = rootRef ? get(rootRef) : document.body;
        const lines = [];
        let size = 0, cut = false;
        function push(depth, text) {
            if (cut) return;
            const line = "  ".repeat(Math.min(depth, 12)) + "- " + text;
            size += line.length + 1;
            if (size > max) { cut = true; return; }
            lines.push(line);
        }
        function walk(el, depth) {
            if (cut || !el || SKIP.has(el.tagName)) return;
            if (el.nodeType === 3) {
                const t = clean(el.textContent, 300);
                if (t.length > 1 && el.parentElement && !interactive(el.parentElement)) push(depth, "text: " + t);
                return;
            }
            if (el.nodeType !== 1 || !shown(el) || el.getAttribute("aria-hidden") === "true") return;
            const role = roleOf(el);
            if (interactive(el)) {
                const r = ref(el);
                const st = state(el);
                push(depth, (role || "clickable") + ' "' + nameOf(el) + '" [ref=' + r + "]" + (st.length ? " " + st.join(" ") : ""));
                if (el.tagName === "SELECT") {
                    Array.from(el.options).slice(0, 30).forEach(o => push(depth + 1, 'option "' + clean(o.text, 60) + '"'));
                    return;
                }
                if (["link", "button"].includes(role) && el.children.length < 3) return;
                for (const c of el.childNodes) walk(c, depth + 1);
                return;
            }
            let d = depth;
            if (role && role !== "listitem" && role !== "form" || el.tagName === "IFRAME") {
                const name = role === "heading" || role === "img" ? nameOf(el) : (el.getAttribute("aria-label") || "");
                push(depth, role + (name ? ' "' + clean(name, 120) + '"' : "") + (state(el).length ? " " + state(el).join(" ") : ""));
                d = depth + 1;
                if (role === "heading" || role === "img") return;
            } else if (role === "listitem") {
                push(depth, "listitem");
                d = depth + 1;
            }
            if (el.shadowRoot) for (const c of el.shadowRoot.childNodes) walk(c, d);
            for (const c of el.childNodes) walk(c, d);
        }
        walk(root, 0);
        return JSON.stringify({ url: location.href, title: document.title, snapshot: lines.join("\n"),
                                truncated: cut, focused: document.activeElement && document.activeElement !== document.body
                                    ? ref(document.activeElement) : "" });
    }

    function text(offset, length) {
        const main = document.querySelector("main, [role=main], article") || document.body;
        const all = clean(main.innerText.replace(/\n{3,}/g, "\n\n"));
        offset = Math.max(0, offset || 0);
        length = Math.min(20000, length || 8000);
        return JSON.stringify({ url: location.href, title: document.title, text: all.slice(offset, offset + length),
                                total: all.length, next: offset + length < all.length ? offset + length : null });
    }

    function point(el) {
        el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
    }
    function mouse(el, type, p) {
        const Ev = type.startsWith("pointer") ? PointerEvent : MouseEvent;
        el.dispatchEvent(new Ev(type, { bubbles: true, cancelable: true, composed: true, view: window, clientX: p.x,
                                        clientY: p.y, button: 0, buttons: type.endsWith("down") ? 1 : 0, pointerType: "mouse" }));
    }
    function click(id) {
        const el = get(id);
        const p = point(el);
        const target = document.elementFromPoint(p.x, p.y);
        const hit = target && (el === target || el.contains(target)) ? target : el;
        ["pointerover", "mouseover", "pointerdown", "mousedown"].forEach(t => mouse(hit, t, p));
        if (hit.focus) hit.focus({ preventScroll: true });
        ["pointerup", "mouseup"].forEach(t => mouse(hit, t, p));
        hit.click();
        return JSON.stringify({ ok: true, clicked: nameOf(el) || roleOf(el), at: p });
    }
    function hover(id) {
        const el = get(id);
        const p = point(el);
        ["pointerover", "pointerenter", "mouseover", "mouseenter", "pointermove", "mousemove"].forEach(t => mouse(el, t, p));
        return JSON.stringify({ ok: true });
    }
    function insert(el, value, clear) {
        el.focus({ preventScroll: false });
        if (clear) {
            if (typeof el.select === "function" && el.tagName !== "SELECT") el.select();
            else document.execCommand("selectAll", false, null);
            if (!value) document.execCommand("delete", false, null);
        }
        if (value && !document.execCommand("insertText", false, value)) {
            // a field the command does not reach (some frameworks): the native setter, then the events
            const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value");
            if (setter && setter.set && "value" in el) setter.set.call(el, (clear ? "" : el.value) + value);
            else el.textContent = (clear ? "" : el.textContent) + value;
            el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
        }
        el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function keyOn(el, key) {
        const code = { Enter: 13, Escape: 27, Tab: 9, ArrowDown: 40, ArrowUp: 38, ArrowLeft: 37, ArrowRight: 39,
                       Backspace: 8, Delete: 46, " ": 32, PageDown: 34, PageUp: 33, Home: 36, End: 35 }[key] || 0;
        const init = { key: key, code: key === " " ? "Space" : key, keyCode: code, which: code, bubbles: true, cancelable: true, composed: true };
        const go = el.dispatchEvent(new KeyboardEvent("keydown", init));
        el.dispatchEvent(new KeyboardEvent("keypress", init));
        el.dispatchEvent(new KeyboardEvent("keyup", init));
        if (go && key === "Enter" && el.form) {
            if (typeof el.form.requestSubmit === "function") el.form.requestSubmit(); else el.form.submit();
        }
        if (go && key === "Tab") {
            const all = Array.from(document.querySelectorAll("a[href],button,input,select,textarea,[tabindex]")).filter(e => shown(e) && e.tabIndex >= 0);
            const i = all.indexOf(el);
            if (i >= 0 && all[i + 1]) all[i + 1].focus();
        }
    }
    function type(id, value, submit, clear) {
        const el = get(id);
        insert(el, String(value || ""), clear !== false);
        if (submit) keyOn(el, "Enter");
        return JSON.stringify({ ok: true, typed: el.type === "password" ? "(hidden)" : clean(el.value || el.innerText, 80) });
    }
    function press(key, id) {
        const el = id ? get(id) : (document.activeElement || document.body);
        keyOn(el, String(key || "Enter"));
        return JSON.stringify({ ok: true });
    }
    function choose(id, value) {
        const el = get(id);
        if (el.tagName !== "SELECT") throw new Error("not a list: click it, then the option");
        const want = String(value || "").toLowerCase();
        const o = Array.from(el.options).find(o => o.value.toLowerCase() === want || clean(o.text).toLowerCase() === want)
            || Array.from(el.options).find(o => clean(o.text).toLowerCase().includes(want));
        if (!o) throw new Error("no option " + value);
        el.value = o.value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        return JSON.stringify({ ok: true, chosen: clean(o.text, 60) });
    }
    function scroll(id, dy) {
        if (id) get(id).scrollIntoView({ block: "center", behavior: "instant" });
        else window.scrollBy(0, dy || innerHeight * 0.8);
        return JSON.stringify({ ok: true, y: Math.round(scrollY), height: document.documentElement.scrollHeight });
    }
    function find(needle) {
        const want = String(needle || "").toLowerCase();
        return JSON.stringify({ found: !!want && document.body.innerText.toLowerCase().includes(want) });
    }

    // ---- the Trousseau: fields found and filled here, the values never go back -------------------------------------
    function loginFields() {
        const inputs = Array.from(document.querySelectorAll("input")).filter(i => shown(i) && !i.disabled && !i.readOnly);
        const pass = inputs.find(i => i.type === "password" && !/new|confirm/i.test(i.autocomplete + i.name + i.id));
        const otp = inputs.find(i => /one-time-code/i.test(i.autocomplete)
            || /otp|totp|2fa|mfa|verification|pin|code/i.test(i.name + " " + i.id + " " + (i.getAttribute("aria-label") || "") + " " + i.placeholder)
               && i.type !== "password" && !/email|user|login/i.test(i.name + i.id));
        const userRe = /user|login|email|e-mail|mail|identif|account|phone|session_key/i;
        let user = inputs.find(i => /username|email/i.test(i.autocomplete) && i.type !== "password");
        if (!user) user = inputs.find(i => (i.type === "email" || userRe.test(i.name + " " + i.id + " " + i.placeholder + " " + (i.getAttribute("aria-label") || ""))) && i !== otp && i.type !== "password" && i.type !== "hidden" && i.type !== "checkbox");
        if (!user && pass) {
            const before = inputs.filter(i => i !== pass && /^(text|email|tel)$/.test(i.type || "text"));
            user = before.filter(i => i.compareDocumentPosition(pass) & Node.DOCUMENT_POSITION_FOLLOWING).pop();
        }
        const form = (pass || user || otp || {}).form;
        let submit = form && (form.querySelector("button[type=submit],input[type=submit]") || form.querySelector("button"));
        if (!submit) submit = Array.from(document.querySelectorAll("button,[role=button],input[type=submit]"))
            .find(b => shown(b) && /connexion|connecter|sign ?in|log ?in|continuer|continue|suivant|next|valider|verify|vérifier|anmelden|weiter/i.test(b.innerText || b.value || ""));
        return { user: user ? ref(user) : "", pass: pass ? ref(pass) : "", otp: otp && otp !== user ? ref(otp) : "",
                 submit: submit ? ref(submit) : "", host: location.hostname };
    }
    function fields() { return JSON.stringify(loginFields()); }
    function fill(id, value) {
        const el = get(id);
        insert(el, String(value || ""), true);
        return JSON.stringify({ ok: true });
    }
    function read(id) {   // only for the Trousseau saving a login the bot just made: never sent to the model
        const el = get(id);
        return JSON.stringify({ value: el.value || "" });
    }

    // ---- Annoter: what is under the person's pointer -------------------------------------------------------------
    function selector(el) {
        if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return "#" + el.id;
        const parts = [];
        for (let e = el; e && e.nodeType === 1 && e !== document.body && parts.length < 5; e = e.parentElement) {
            let p = e.tagName.toLowerCase();
            const cls = Array.from(e.classList).filter(c => /^[A-Za-z][\w-]{1,30}$/.test(c)).slice(0, 2);
            if (cls.length) p += "." + cls.join(".");
            const sib = e.parentElement ? Array.from(e.parentElement.children).filter(s => s.tagName === e.tagName) : [];
            if (sib.length > 1) p += ":nth-of-type(" + (sib.indexOf(e) + 1) + ")";
            parts.unshift(p);
            if (e.id) { parts[0] = "#" + e.id; break; }
        }
        return parts.join(" > ");
    }
    function pick(x, y) {
        const el = document.elementFromPoint(x, y);
        if (!el) return JSON.stringify({});
        const r = el.getBoundingClientRect();
        const st = getComputedStyle(el);
        return JSON.stringify({ ref: ref(el), tag: el.tagName.toLowerCase(), role: roleOf(el), name: nameOf(el),
                                text: clean(el.innerText || el.value || "", 200), selector: selector(el),
                                rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
                                style: { color: st.color, background: st.backgroundColor, font: st.fontSize + " " + st.fontFamily.split(",")[0],
                                         margin: st.margin, padding: st.padding } });
    }
    function rect(x, y) {
        const r = JSON.parse(pick(x, y)).rect;
        return JSON.stringify(r || {});
    }

    function guard(fn) {
        return function () {
            try { return fn.apply(null, arguments); }
            catch (e) { return JSON.stringify({ error: String(e && e.message || e) }); }
        };
    }
    return { snapshot: guard(snapshot), text: guard(text), click: guard(click), hover: guard(hover), type: guard(type),
             press: guard(press), choose: guard(choose), scroll: guard(scroll), find: guard(find), fields: guard(fields),
             fill: guard(fill), read: guard(read), pick: guard(pick), rect: guard(rect) };
})();
