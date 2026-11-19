# RE:VERSE — A+D mix system ("Clean Diary")

Builders follow this exactly. Canvas file rules in BRIEF.md still apply (support.js, one css2 link in `<helmet>`, inline styles, inline stroke SVG icons, real elements, no emoji, contrast ≥ 4.5:1).

---

## 1. Intent

From **D (Listening Diary)** we keep the things the owner liked: large album covers as the main visual, the diary margin (day number + weekday beside each entry), the lyric line set big in a serif so the song's words read apart from the user's words, and ink-black active states. From **A (Native Clean)** we take restraint: a large page title as the header, hairline inset lists, a segmented control for record kinds, edit/delete behind a "…" menu, and plain grouped settings rows. **Dropped entirely:** the year-in-review / 결산 (genre bar, monthly bars, "가장 많이 기록한 앨범", any chart), pills/badges, eyebrow labels, stat tiles, outline buttons, icons in front of labels, cards around content, gray 8px bands on desktop, and the header tagline. One accent, used rarely; everything else is ink on white.

---

## 2. Tokens

### Color

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `ground` | `#ffffff` | page background (desktop + mobile) | — |
| `surface` | `#f2f3f5` | search field, segmented track, mobile section band (8px), avatar fallback is `#e9ebee` | — |
| `text-1` | `#16181c` | titles, lyric, active states, numbers | 17.8:1 on ground · 16.0:1 on surface |
| `text-2` | `#4a5059` | reflection body, artist · album, values, inactive tabs | 8.1:1 on ground · 7.3:1 on surface |
| `text-3` | `#626872` | meta (visibility), weekday, counts, placeholder | 5.6:1 on ground · 5.0:1 on surface |
| `hairline` | `#e6e8eb` | 1px separators | — |
| `accent` | `#d41352` | filled stars, "모두 보기"/"전체 24" links, "2건", saved bookmark, ":" in wordmark, focus ring | 5.2:1 on ground · 4.7:1 on surface |
| `accent-pressed` | `#b00f44` | :active / pressed accent text and icons | 7.0:1 on ground |
| `destructive` | `#c4161c` | "삭제" menu item, "로그아웃" | 6.0:1 on ground |
| `icon-quiet` | `#8a919c` | empty-star outline, chevrons (graphics only, never text) | 3.2:1 (graphic, ≥3:1) |

Accent is never a background fill, never on active tabs/nav (those are `text-1`). Shadows exist only on the segmented selected segment and the open "…" menu.

### Fonts

Paste verbatim inside `<helmet>`:

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;600;700&family=Noto+Serif+KR:wght@500&display=swap">
```

- UI stack (root): `font-family: 'Inter', 'Noto Sans KR', -apple-system, 'Apple SD Gothic Neo', sans-serif;` Inter renders Latin and numbers, Noto Sans KR renders Hangul. Root also gets `font-variant-numeric: tabular-nums; -webkit-font-smoothing: antialiased;`
- Lyric stack (lyric lines only): `font-family: 'Noto Serif KR', 'Nanum Myeongjo', serif; font-weight: 500;` **Kept on purpose:** at 19–22px it is very legible and tells the song's words apart from the user's reflection without quote marks, rules or color. It is never used for UI, titles or reflections.

### Type scale (px size / line-height, weight, letter-spacing)

| Role | Desktop (≥900) | Mobile (<600) |
|---|---|---|
| Page title (h1) | 40/48, 700, -0.025em | 32/40, 700, -0.02em |
| Section title (h2) | 20/28, 700, -0.015em | 18/26, 700, -0.01em |
| Profile name | 28/36, 700, -0.02em | 22/28, 700, -0.02em |
| Item title (song in entry) | 18/26, 600 | 16/22, 600 |
| Item title (song row / tile) | 16/22, 600 (tile 14/20) | 15/21, 600 (tile 13/18) |
| Lyric quote (serif) | 22/34, 500, -0.01em | 19/30, 500, -0.01em |
| Reflection body | 16/27, 400, text-2 | 15/24, 400, text-2 |
| Diary day number | 30/34, 600, -0.02em | 22/26, 600 |
| Body / row label | 15/22, 400–500 | 15/22 |
| Meta (artist · album, counts) | 14/20 text-2 · 13/18 text-3 | 13/18 |
| Label (weekday, tile meta, tab bar) | 13/18 text-3 | 12/16 text-3 · tab bar 11/14 |

Minimum text size anywhere: 11px (tab bar labels only); 12px everywhere else.

### Spacing (8px grid, 4 allowed for tight pairs)

`4 · 8 · 12 · 16 · 24 · 32 · 40 · 48 · 64 · 72`. Desktop: side gutter = centered container; section gap 48; entry padding 24 vertical. Mobile: side gutter 16; entry padding 20 vertical; section separation = 8px `surface` band.

### Radii

- Covers: **6px** at every size (no larger radius on big covers). Add `outline: 1px solid rgba(22,24,28,0.06); outline-offset: -1px;` so light covers keep an edge.
- Controls: search field + segmented track **10px**, segment **8px**, "…" menu **12px**, "…" pressed halo 50%. Avatar 50%.
- Nothing else is rounded (no cards exist).

### Hairlines

`1px solid #e6e8eb`. List separators are **inset** to the start of the text/cover column (A-style), never full-bleed inside a column. Full-bleed only: under the desktop header, above the mobile tab bar. No vertical rules.

---

## 3. Components

All icons: inline SVG 24×24 viewBox, `fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"`. Shared paths:

- home `<path d="M4 10.5L12 4l8 6.5V20h-5v-6H9v6H4z"/>`
- friends `<circle cx="9" cy="8" r="3.5"/><path d="M2.5 19.5c.6-3.3 3.1-5.5 6.5-5.5s5.9 2.2 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.6c1.8.8 3 2.5 3.5 4.9"/>`
- AI 추천 (broadcast, no sparkles) `<circle cx="12" cy="12" r="2"/><path d="M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8"/>`
- 나의 기록 (note) `<path d="M9 18V5.5l11-2V16"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>`
- search `<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>`
- more (…) `fill="currentColor" stroke="none"`: `<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>`
- bookmark `<path d="M6.5 3.5h11v17l-5.5-4-5.5 4z"/>` (saved: `fill="currentColor"`, color accent; not saved: no fill, color text-3)
- lock `<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>`
- chevron `<path d="M9 6l6 6-6 6"/>` (16px, color icon-quiet)
- star `<path d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3-4.6-4.4 6.3-.9z"/>`

### 3.1 Desktop header (≥900px)

- `<header>` full-bleed, height **64**, background ground, bottom hairline. Inner: max-width 1200, margin 0 auto, `display:flex; align-items:center`.
- Wordmark `<a href="#home">RE<span style="color:#d41352">:</span>VERSE</a>`: Inter 700, 19px, letter-spacing -0.02em, text-1. No tagline.
- `<nav aria-label="주 메뉴">` **left-aligned**, margin-left 48, gap 28. Items in this order: **홈** (#home), **친구** (#friends), **AI 추천** (#ai), **나의 기록** (#records). Each `<a>`: height 64, `display:flex; align-items:center; box-sizing:border-box; border-bottom:2px solid transparent; padding-top:2px;` 15px, weight 500, text-2. Active: text-1, 600, `border-bottom-color:#16181c`, `aria-current="page"`. No icons in desktop nav.
- Right (margin-left auto): `<a href="#account" aria-label="내 계정">` = avatar 32 circle (`#e9ebee`, initial "음" 14px 600 text-1) + name "음악 산책자" 14px 500 text-1, gap 10, height 44. On the account screen: `aria-current="page"`, name weight 600, and a 2px text-1 bottom border on the link (same as nav active).

### 3.2 Mobile header + bottom tab bar (<600px)

- Header: height 52, padding 0 4px 0 16px, wordmark 17px; right: avatar 32 inside a 44×44 link to #account. No hairline under it (title follows).
- Tab bar: fixed bottom (in a static artboard: last child, `margin-top:auto`), height 64 (+ safe area in real app), top hairline, ground background, `display:grid; grid-template-columns:repeat(4,1fr)`. Items 홈 · 친구 · AI 추천 · 나의 기록: icon 24 over label 11/14 500, gap 3, color text-3; active: text-1, label 700, icon stroke-width 2.2, `aria-current="page"`. On 내 계정 no tab is active (account is the avatar).

### 3.3 Segmented control (record kinds)

`<div role="tablist" aria-label="기록 종류">`, track: surface, radius 10, padding 2, height 44 (box-sizing border-box), inline-flex.
Segments `<button role="tab">`: height 40, radius 8, padding 0 20px (desktop) / `flex:1; padding:0` (mobile, full width), label 15px (mobile 14px). Label + count with gap 6: "코멘트 24", "기록한 음악 31", "저장한 곡 12".
- Selected: background `#ffffff`, `box-shadow: 0 1px 3px rgba(22,24,28,0.12), 0 0 0 0.5px rgba(22,24,28,0.06)`, label text-1 600, count text-2 600.
- Unselected: transparent, label text-2 500, count text-3 500.

### 3.4 Search field

`<label>` wrapper: surface, radius 10, height 44, padding 0 12, gap 8; search icon 18 text-3; `<input type="search" aria-label="기록 검색" placeholder="곡명, 가수, 가사, 코멘트 검색">` 15px text-1, transparent, no border; placeholder text-3 (5.0:1 on surface). Desktop width 352 (sits right of the page title, aligned with the rail). Mobile full width.

### 3.5 Visibility filter (comments only)

`<div role="group" aria-label="공개 범위">` of three text buttons, no backgrounds, gap 20 (mobile 16): `전체` · `친구 공개 15` · `나만 보기 9`. Each: height 44, 15px; selected text-1 600 `aria-pressed="true"`; unselected text-2 500; count in text-3. Desktop: right end of the toolbar row. Mobile: own row under the segmented control, left-aligned (first button text at x=16).

### 3.6 Comment entry (the diary entry) — core component

`<article>`; separator: `border-bottom` hairline inset from the cover column.

**Desktop (main column 776px):**
- `display:grid; grid-template-columns:56px 136px minmax(0,1fr); column-gap:24px; padding:24px 0; align-items:start;`
- Col 1 **date margin** `<time datetime="2026-11-17">`: day "17" 30/34 600 text-1, under it weekday "화" 13/18 text-3 (margin-top 2). Left-aligned. Absolute dates only (no "어제").
- Col 2 **cover** `<img>` 136×136, radius 6, cover outline, `alt=""` (song title is adjacent text).
- Col 3 body:
  - Title row `display:flex; align-items:flex-start; justify-content:space-between;`: song title `<a href="#">` 18/26 600 text-1; "…" button 44×44, `margin:-9px -10px 0 0`, color text-3, `aria-label="코멘트 메뉴" aria-haspopup="menu" aria-expanded="false"`.
  - Artist · album 14/20 text-2, margin-top 2 ("유월 · Blue Hour").
  - Lyric `<blockquote>` margin 16 0 0, serif 22/34 500 text-1. **No quote marks, no left bar, no background.**
  - Reflection `<p>` margin 8 0 0, 16/27 text-2, max-width 34em.
  - Meta margin-top 14, 13/18 text-3: either `친구 공개` (plain text) or lock icon 13px + `나만 보기` (gap 4). This is the only icon in the entry body.
- Separator: hairline from x = 80 (start of cover column) to the right edge, i.e. `margin-left:80px` on a bottom rule (or use border on an inner wrapper).
- Height ≈ 236px with a one-line lyric and a two-line reflection.

**Mobile (390):**
- Row A: `grid-template-columns:36px 88px minmax(0,1fr) 44px; column-gap:12px; padding:20px 4px 0 16px;` date margin (day 22/26 600, weekday 12/16 text-3) · cover 88×88 · stack (title 16/22 600; artist · album 13/18 text-2, may wrap to 2 lines; meta 13/18 text-3 margin-top 6) · "…" 44×44 at top (margin-top -10).
- Row B: `padding:14px 16px 20px 64px;` (aligned with cover's left edge) lyric serif 19/30 500, reflection 15/24 text-2 margin-top 6.
- Hairline inset at left 64.

### 3.7 Song row (기록한 음악 / 저장한 곡 in list form)

**Rating: 5 SVG stars**, gap 2, filled star `fill="#d41352" stroke="none"`, empty star `fill="none" stroke="#8a919c" stroke-width="1.6"`; wrapper `role="img" aria-label="별점 5점 중 4점"`. Size 14 (desktop rail and list), 13 (mobile), 12 (tiles). No rating: text "별점 없음" text-3 at meta size.

**Saved/recorded state without pills:** saved = trailing bookmark button, filled, accent, `aria-pressed="true" aria-label="저장됨"`; not saved = outline, text-3, `aria-pressed="false" aria-label="저장하기"`. Recorded = the row carries a record date ("11월 15일 기록") in meta; a saved-but-not-recorded song shows "아직 기록 전" in text-3 instead of stars.

- Rail / compact (desktop rail 352): `grid-template-columns:64px minmax(0,1fr) 44px; column-gap:16px; align-items:center; padding:12px 0;` cover 64. Text: title 16/22 600 · "모브 · Sunday Window" 13/18 text-2 · line 3 (margin-top 4): stars 14 + "코멘트 2" 13/18 text-3, gap 10 (no comments → "코멘트 없음"). Bookmark 44×44 at right (`margin-right:-10px`). Hairline inset at 80.
- Full list (if a builder shows the 기록한 음악 tab on desktop): `grid-template-columns:56px 88px minmax(0,1fr) 44px; column-gap:24px; padding:20px 0;` date margin = record date (same style as 3.6), cover 88, title 17/24 600, artist · album 14/20 text-2, line 3 stars 14 + "코멘트 n".
- Mobile: `grid-template-columns:64px minmax(0,1fr) 44px; column-gap:12px; padding:12px 4px 12px 16px;` cover 64, title 15/21, meta 13/18; line 3 stars 13 + "11월 15일 · 코멘트 2" 13 text-3. Hairline inset at 92.

### 3.8 Cover grid tile

`<a>` flex column, min-width 0. Cover `width:100%; aspect-ratio:1/1; object-fit:cover;` radius 6 + outline. Title 14/20 600 margin-top 10 (mobile 13/18, margin-top 8), single line ellipsis. Second line 13/18 text-2 ("유월 · Blue Hour"; album tiles just "유월"). Optional third line margin-top 4: stars 12, or "별점 없음" 12/16 text-3. Grids: desktop rail 2 cols gap 24 (tiles 164); desktop account 3 cols gap 24 (tiles ~243); mobile 3 cols, column-gap 12, row-gap 20.

### 3.9 Section header

`display:flex; align-items:baseline; justify-content:space-between;` h2 (section title size) with count in text-3 same size weight 500 ("기록한 음악 **31**" → "31" text-3); right: text link in accent, 14px 500, height 44 (`display:flex; align-items:center`): "모두 보기" or "전체 24". Margin-bottom 8 (desktop) / height 56 row (mobile). No icons, no eyebrow above.

### 3.10 Profile header

- Desktop (left column 352): avatar 88×88 circle `#e9ebee`, initial "음" 34px 600 text-1 (an `<img>` if a photo existed — none here). Name margin-top 20 (28/36 700). Handle "@walker" 15/22 text-2. Stats margin-top 20.
- Mobile: row, gap 16, padding 8 16 0: avatar 72 (initial 28px) + stack (name 22/28 700, handle 14/20 text-2). Stats below, padding 16 16 20.

### 3.11 Stats (inline, NOT a 결산)

`<nav aria-label="내 활동">` with four links, `display:flex; flex-wrap:wrap; column-gap:20px; row-gap:8px;` (mobile column-gap 16). Each `<a>`: `<span>` number 17px 700 text-1 tabular + space + label 15px 400 text-2, baseline aligned, height 32 (tap area extends via padding 6 0). Order: **24** 코멘트 · **12** 저장한 곡 · **31** 기록한 음악 · **8** 친구. No tiles, no borders, no icons, no dividers, no centering. Nothing else (no genres, months, totals by period).

### 3.12 Settings rows

A plain list, no container. Top hairline above first row; hairline between rows; bottom hairline after last.
- Row `<a>`: height 52, `display:flex; align-items:center; gap:8px;` label 15/22 400 text-1 (flex 1); value 15/22 text-2; chevron 16 icon-quiet.
  - `표시 이름` — value "음악 산책자" — opens the editor.
  - `받은 친구 요청` — value **"2건"** in accent 600 — links to #friends. `aria-label="받은 친구 요청 2건"`.
- `로그아웃`: separate `<button type="button">`, margin-top 24, height 52, left-aligned, 15px 500 destructive, no chevron, no border, no background.
- Editor state (only if a builder shows it): the 표시 이름 row expands to a 44px input (surface, radius 10, 15px) with trailing "5/40" 12px text-3, then two text buttons right-aligned: "취소" text-2, "저장" text-1 600. No helper sentence.

### 3.13 "…" menu (shown open exactly once, on the 2nd comment entry of 나의 기록)

- Trigger in pressed state: `aria-expanded="true"`, icon text-1, a 32px circle `rgba(22,24,28,0.08)` behind the dots.
- `<div role="menu" aria-label="코멘트 메뉴">`: positioned absolute, right edge aligned to the trigger's right edge, top = trigger bottom + 4. Width 220, background ground, radius 12, `box-shadow: 0 10px 32px rgba(22,24,28,0.16), 0 0 0 1px rgba(22,24,28,0.06)`, padding 6 0.
- Items `<button role="menuitem">`: height 44, padding 0 16, 15px text-1, left-aligned, **text only, no icons**: `코멘트 수정` · `친구 공개로 바꾸기` (or `나만 보기로 바꾸기` if the entry is public) · `곡 보기` · hairline (margin 6 0) · `삭제` in destructive.

### 3.14 Focus / hover (desktop)

Focus: `outline:2px solid #d41352; outline-offset:2px;`. Hover: song-title links get underline (1px, offset 3); cover links `opacity:.92`. No hover backgrounds on rows.

---

## 4. Desktop layout (reference 1440×810; also 1920×1080)

Container: `max-width:1200px; margin:0 auto;` (at 1440 → 120px side margins; at 1920 → 360px, header inner aligns with content edges). Ground is white edge to edge; no side panels, no stretched cards. Artboards: width 1440, height = full page (e.g. 1300–1500), and **everything listed under "above the fold" must sit inside y ≤ 810**.

Grid: **main 776px + rail/side 352px, column-gap 72px** (= 1200). 900–1279px: container `padding:0 40px`, side column 320px, gap 48. <900px: one column (see collapse). <600px: mobile spec.

### 4.1 나의 기록 (records) — chosen pattern: diary list + right rail

```
y=0    header 64
y=104  title row (padding-top 40): h1 "나의 기록" left | search field 352 right (vertically centered on 48px row)
y=152  +24
y=176  ┌ main 776 ───────────────────────────────┐  ┌ rail 352 ─────────────┐
       │ toolbar 44: segmented (left) ·          │  │ section hdr 44:        │
       │   visibility filter (right)             │  │ 기록한 음악 31 · 모두 보기│
y=236  │ month row 40: "2026년 11월" 15/22 600 + │  │ 3 compact song rows    │
       │   "4개" text-3, bottom hairline          │  │   (88 each)            │
y=276  │ entry 1 (~236)                          │  │ +40                    │
y=512  │ entry 2 (~236)  ← "…" menu open here    │  │ 저장한 곡 12 · 모두 보기 │
y=748  │ entry 3 begins (date + cover top peek)  │  │ 2×2 tiles (164)        │
       └─────────────────────────────────────────┘  └────────────────────────┘
```

Rail scrolls with the page (not sticky): with both sections it is taller than a 16:9 viewport. Above the fold: title, search, segmented control, filter, 2 full comment entries, 3 song rows, top row of 저장한 곡 tiles. Page continues: entry 3, entry 4, then a quiet "더 보기" text button (15px 500 text-2, height 44), left-aligned with the cover column (x = 80 inside main), not centered.

### 4.2 내 계정 (account) — profile column left + content right

```
y=0    header 64 (account link active)
y=104  h1 "내 계정" (padding-top 40), 48px row
y=184  ┌ side 352 ─────────────┐  ┌ main 776 ──────────────────────────────┐
       │ avatar 88             │  │ section hdr: 즐겨 듣는 앨범 · (no link)  │
       │ name 28/36 · @walker  │  │ 3 album tiles, 3 cols gap 24 (~243 each)│
       │ stats inline (2 lines)│  │   + title/artist (~290 total)           │
       │ +40                   │  │ +48                                     │
       │ settings rows 52×2    │  │ section hdr: 최근 코멘트 · 전체 24        │
       │ 로그아웃 (mt 24)       │  │ comment entry 1 (same as 3.6)           │
       └───────────────────────┘  │ comment entry 2, 3 (below fold)         │
                                   └─────────────────────────────────────────┘
```

Profile and settings sit in the left column in DOM reading order (profile, content, settings) so keyboard order matches the stacked mobile order. Above the fold: title, full profile column incl. 로그아웃 (~y 700), three big album covers, and 최근 코멘트 header + entry 1 top.

### 4.3 Collapse <900px

Records: single column, max-width 776 centered with 32px gutter; search moves under the title (full width); rail sections follow the list as normal sections (song rows full width, 저장한 곡 tiles 4 across). Account: profile switches to the mobile row form (avatar 72 + name) with stats inline under it; then 즐겨 듣는 앨범, 최근 코멘트, then settings rows + 로그아웃 at the bottom. Header keeps text nav until 600px; below 600 the bottom tab bar replaces it.

---

## 5. Mobile layout (390 wide)

Gutter 16. Root `display:flex; flex-direction:column`, tab bar last with `margin-top:auto`. Sections separated by an 8px `surface` band (mobile only).

**나의 기록:** header 52 → h1 32/40 (padding 4 16 0) → search (margin 12 16 0) → segmented full width (margin 12 16 0) → visibility filter row (padding 4 16 0, bottom hairline full width) → month row (height 40, 15/22 600 + count, padding 0 16) → comment entries 1–3 (3.6 mobile) → band → section "기록한 음악 31 · 모두 보기" + 3 song rows (3.7 mobile) → band → "저장한 곡 12 · 모두 보기" + 3 tiles → tab bar (나의 기록 active). "…" menu open on entry 2, same spec, right-aligned at 12px from the edge. Suggested height ~1500.

**내 계정:** header 52 → h1 "내 계정" → profile row (3.10 mobile) → stats inline one line → band → "즐겨 듣는 앨범" 3 tiles → band → "최근 코멘트 · 전체 24" + entries 1–2 → band → settings rows (padding 0 16, hairlines inset 16) + 로그아웃 → tab bar (none active). Suggested height ~1450.

---

## 6. Content plan (identical on desktop and mobile)

Dates: today is 2026-11-18 (수). Weekdays: 17 화, 16 월, 15 일, 14 토, 12 목, 10 화, 9 월.
Covers: Blue Hour `/_blob/8586c0c9d2d35aed390feff86dffbaa0` · Sunday Window `/_blob/a95cb6727950dc9f6775eac769e4ccd3` · Night Drive `/_blob/9ca95933d821bef0ef0de6a40f1864cb`.

### Comments (records list order; account 최근 코멘트 uses #1–#3)

| # | Date | Song · artist · album | Lyric | Reflection | Visibility |
|---|---|---|---|---|---|
| 1 | 17 화 | 푸른 시간 · 유월 · Blue Hour | 해가 저문 자리에 나를 내려놓고 | 퇴근길 버스에서 이 줄 듣고 창밖만 봤다. 오늘은 그냥 이걸로 됐어. | 친구 공개 |
| 2 | 16 월 | 느린 일요일 · 모브 · Sunday Window | 식어 가는 커피에도 향기는 남아 | 일요일 아침마다 틀어 두는 곡. 커피가 식는 것도 괜찮다는 말이 좋다. | 나만 보기 (menu open → shows "친구 공개로 바꾸기") |
| 3 | 12 목 | 우회로 · OFFDAY · Night Drive | 조금 먼 길로 돌아가도 좋아 | 돌아가는 길이 더 좋았던 날들이 생각났다. 그때도 이 노래였나. | 친구 공개 |
| 4 | 9 월 | 새벽의 문장 · 유월 · Blue Hour | 끝내 보내지 못할 문장을 써 | 보내지 못한 메시지가 아직 메모장에 있다. 지우지도 못하고 그냥 둔다. | 나만 보기 |

Month row: "2026년 11월" + "4개". Filter counts: 전체 (24 in tab), 친구 공개 15, 나만 보기 9.

### 기록한 음악 31 (rail / mobile section, 3 rows)

| Song · artist · album | Rating | Comments | Saved | Record date |
|---|---|---|---|---|
| 볕이 드는 자리 · 모브 · Sunday Window | 5 | 코멘트 2 | saved | 11월 15일 |
| 도시의 잔상 · OFFDAY · Night Drive | 4 | 코멘트 1 | not saved | 11월 14일 |
| 새벽의 문장 · 유월 · Blue Hour | 4 | 코멘트 1 | saved | 11월 10일 |

### 저장한 곡 12 (tiles: desktop 4 = 2×2, mobile first 3)

1. 우리가 남긴 파도 · 유월 · Blue Hour — 별점 없음 (아직 기록 전)
2. 우회로 · OFFDAY · Night Drive — 4
3. 볕이 드는 자리 · 모브 · Sunday Window — 5
4. 새벽의 문장 · 유월 · Blue Hour — 4

### Account

Avatar "음", 음악 산책자, @walker. Stats 24 코멘트 · 12 저장한 곡 · 31 기록한 음악 · 8 친구. 즐겨 듣는 앨범: Blue Hour / 유월, Sunday Window / 모브, Night Drive / OFFDAY (title + artist only, no play counts). Settings: 표시 이름 › 음악 산책자 · 받은 친구 요청 › 2건 · 로그아웃.

---

## 7. Do not (specific to this mix)

1. No 결산 of any kind: no genre bar, monthly bars, "가장 많이 기록한", "2026년의 기록", percentages or period totals. The four inline stats are the only numbers on 내 계정.
2. No pills/badges: visibility, saved, recorded, and "2건" are plain text or an icon. No red count bubble.
3. No eyebrow/uppercase labels, no tagline in the header, no section subtitles explaining the section.
4. No cards: entries, rows, profile and settings sit directly on white, separated by hairlines and space. No 8px gray bands on desktop.
5. Do not shrink covers to thumbnail size in comment entries (desktop 136, mobile 88; rail rows 64 is the minimum anywhere).
6. Do not put quote marks, a left bar, italics or a tinted box around the lyric; the serif at size does the work. Serif is for lyrics only.
7. Accent only for the uses listed in tokens. Active tab, nav and segment are ink, not accent. No second accent, no gradients, no colored backgrounds.
8. No icons before labels (nav on desktop, settings rows, menu items, section titles). Icons allowed: tab bar, search, "…", bookmark, lock in meta, stars, chevrons.
9. No centered layouts on desktop: title, toolbar and lists start on the container's left edge; don't center stats or the profile.
10. No helper text under controls, no edit/delete buttons visible on entries (only in the "…" menu), no relative dates ("어제") in the diary margin.
