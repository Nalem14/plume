// Repetitions and reminders of an event in words (editor, card, settings). r is the repeat of ical.repeat_info:
// {freq, interval, byday, monthly ("day"|"weekday"), nth, count, until, editable}.
.pragma library

var DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
var WORKDAYS = ["MO", "TU", "WE", "TH", "FR"]

function dayCode(d) { return DAYS[(d.getDay() + 6) % 7] }
function nthOf(d) { return Math.floor((d.getDate() - 1) / 7) + 1 }
function jsDay(code) { return (DAYS.indexOf(code) + 1) % 7 }
function same(a, b) { return a.length === b.length && a.every(x => b.indexOf(x) >= 0) }

function empty() { return { freq: "", interval: 1, byday: [], monthly: "day", nth: 0, count: 0, until: "", editable: true } }

// The preset of the editor's list for a rule (custom: anything else the editor can write)
function presetOf(r, start) {
    if (!r || !r.freq) return "none"
    if (r.editable === false) return "keep"
    const one = (r.interval || 1) === 1
    const days = r.byday || []
    if (one && (r.freq === "WEEKLY" || r.freq === "DAILY") && same(days, WORKDAYS)) return "WEEKDAYS"
    if (one && r.freq === "DAILY" && !days.length) return "DAILY"
    if (one && r.freq === "WEEKLY" && (!days.length || same(days, [dayCode(start)]))) return "WEEKLY"
    if (one && r.freq === "MONTHLY" && r.monthly !== "weekday") return "MONTHLY"
    if (one && r.freq === "MONTHLY" && r.monthly === "weekday") return "MONTHLY_NTH"
    if (one && r.freq === "YEARLY") return "YEARLY"
    return "custom"
}

// The rule of a preset (its end, count or until, is kept from the current one)
function fromPreset(p, start, current) {
    const r = empty()
    r.count = current ? current.count || 0 : 0
    r.until = current ? current.until || "" : ""
    if (p === "DAILY") r.freq = "DAILY"
    else if (p === "WEEKDAYS") { r.freq = "WEEKLY"; r.byday = WORKDAYS.slice() }
    else if (p === "WEEKLY") { r.freq = "WEEKLY"; r.byday = [dayCode(start)] }
    else if (p === "MONTHLY") r.freq = "MONTHLY"
    else if (p === "MONTHLY_NTH") { r.freq = "MONTHLY"; r.monthly = "weekday"; r.nth = nthOf(start) > 4 ? -1 : nthOf(start) }
    else if (p === "YEARLY") r.freq = "YEARLY"
    else if (p === "custom") {
        const base = current && current.freq ? current : { freq: "WEEKLY", interval: 1, byday: [dayCode(start)], monthly: "day", nth: 0 }
        r.freq = base.freq; r.interval = base.interval || 1; r.byday = (base.byday || []).slice()
        r.monthly = base.monthly || "day"; r.nth = base.nth || 0
    }
    return r
}

function dayName(code, loc, format) { return loc.dayName(jsDay(code), format) }
function list(items, t) {
    if (items.length < 2) return items.join("")
    return items.slice(0, -1).join(", ") + " " + t.rep_and + " " + items[items.length - 1]
}
function nthText(n, t) { return n === -1 ? t.rep_last : t["rep_nth_" + n] || String(n) }

// "Toutes les 2 semaines le mardi et le jeudi, jusqu'au 31 déc." — the whole rule in one line
function describe(r, start, loc, t) {
    if (!r || !r.freq) return ""
    if (r.editable === false) return t.rep_custom_kept
    const n = r.interval || 1
    const days = (r.byday || []).slice().sort((a, b) => DAYS.indexOf(a) - DAYS.indexOf(b))
    let text
    if ((r.freq === "WEEKLY" || r.freq === "DAILY") && n === 1 && same(days, WORKDAYS)) text = t.rep_weekdays
    else if (r.freq === "DAILY") text = n === 1 ? t.rep_daily : t.rep_every_days.replace("%1", n)
    else if (r.freq === "WEEKLY") {
        const names = list((days.length ? days : [dayCode(start)]).map(d => dayName(d, loc, 0)), t)
        text = (n === 1 ? t.rep_weekly_on : t.rep_every_weeks_on.replace("%2", n)).replace("%1", names)
    } else if (r.freq === "MONTHLY") {
        const what = r.monthly === "weekday"
            ? t.rep_month_nth.replace("%1", nthText(r.nth || nthOf(start), t)).replace("%2", dayName(dayCode(start), loc, 0))
            : t.rep_month_day.replace("%1", start.getDate())
        text = (n === 1 ? t.rep_monthly : t.rep_every_months.replace("%2", n)).replace("%1", what)
    } else if (r.freq === "YEARLY") {
        const what = loc.toString(start, "d MMMM")
        text = (n === 1 ? t.rep_yearly : t.rep_every_years.replace("%2", n)).replace("%1", what)
    } else return t.rep_custom_kept
    if (r.count > 0) text += ", " + (r.count === 1 ? t.rep_once : t.rep_times.replace("%1", r.count))
    else if (r.until) text += ", " + t.rep_until.replace("%1", loc.toString(new Date(r.until + "T00:00"), "d MMM yyyy"))
    return text
}

// The editor's list: [{text, value}] for this start (the labels say the day: "Chaque semaine le mardi")
function presets(start, loc, t, kept) {
    const out = [{ text: t.repeat_, value: "none" }]
    out.push({ text: t.rep_daily, value: "DAILY" })
    out.push({ text: t.rep_weekdays, value: "WEEKDAYS" })
    out.push({ text: t.rep_weekly_on.replace("%1", dayName(dayCode(start), loc, 0)), value: "WEEKLY" })
    out.push({ text: t.rep_monthly.replace("%1", t.rep_month_day.replace("%1", start.getDate())), value: "MONTHLY" })
    const nth = nthOf(start) > 4 ? -1 : nthOf(start)
    out.push({ text: t.rep_monthly.replace("%1", t.rep_month_nth.replace("%1", nthText(nth, t)).replace("%2", dayName(dayCode(start), loc, 0))), value: "MONTHLY_NTH" })
    out.push({ text: t.rep_yearly.replace("%1", loc.toString(start, "d MMMM")), value: "YEARLY" })
    out.push({ text: t.rep_custom, value: "custom" })
    if (kept) out.push({ text: t.rep_custom_kept, value: "keep" })
    return out
}

// ---- reminders: minutes before the start (negative: after it, as "9:00 on the day" of an all-day event) ----
var TIMED = [0, 5, 10, 15, 30, 60, 120, 1440, 2880, 10080]
var ALL_DAY = [-540, 900, 2340, 9540]

function pad(n) { return (n < 10 ? "0" : "") + n }
function alarmLabel(m, allDay, t) {
    m = parseInt(m)
    if (isNaN(m)) return ""
    if (allDay) {
        const days = Math.max(0, Math.ceil(m / 1440))
        const at = days * 1440 - m
        if (at >= 0 && at < 1440) {
            const hm = pad(Math.floor(at / 60)) + ":" + pad(at % 60)
            if (days === 0) return t.alarm_same_day.replace("%1", hm)
            if (days === 1) return t.alarm_day_before.replace("%1", hm)
            if (days === 7) return t.alarm_week_before_at.replace("%1", hm)
            return t.alarm_days_before_at.replace("%1", days).replace("%2", hm)
        }
    }
    if (m === 0) return t.alarm_at_start
    if (m < 0) return t.alarm_after.replace("%1", -m)
    if (m % 10080 === 0) return m === 10080 ? t.alarm_week : t.alarm_weeks.replace("%1", m / 10080)
    if (m % 1440 === 0) return m === 1440 ? t.alarm_day : t.alarm_days.replace("%1", m / 1440)
    if (m % 60 === 0) return m === 60 ? t.alarm_hour : t.alarm_hours.replace("%1", m / 60)
    return t.alarm_minutes.replace("%1", m)
}
// A timed reminder for an all-day event (and back) when "all day" is switched
function convert(m, toAllDay) {
    m = parseInt(m)
    if (toAllDay) return m <= 0 ? -540 : m < 1440 ? 900 : m >= 10080 ? 9540 : 900 + Math.floor(m / 1440 - 1) * 1440
    return m <= 0 ? 0 : m <= 900 ? 1440 : m >= 9540 ? 10080 : Math.round((m + 540) / 1440) * 1440
}
