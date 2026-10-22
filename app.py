# =====================================================================
# Procurement Agent — Production Streamlit UI
# Preserves: ERPNext + LangGraph + MCP backend contract (SSE, structured_doc)
# Enhancements: centered shell under sidebar collapse, animated thinking
# state with stages, discrete PR drawer, enterprise design system.
# =====================================================================
import asyncio
import inspect
import json
import time
import uuid
from datetime import date
from typing import Any, AsyncGenerator, Dict, Generator, Optional, Tuple

import httpx
import streamlit as st
from login_ import AUTH_COOKIE_NAME, clear_authentication, render_login_page
from config.settings import settings
# ---------------------------------------------------------------------
# Configuration (backend contract unchanged)
# ---------------------------------------------------------------------
BASE_API_URL = settings.BASE_API_URL
FASTAPI_STREAM_URL = f"{BASE_API_URL}/api/v1/chat/stream"
DEPARTMENTS = ["IT", "Sales", "HR", "Finance", "Operations"]
UOMS = ["Nos", "Kg", "Box", "Set", "Litre", "Meter"]

# Cross-version fill helper (older `use_container_width`, newer `width="stretch"`)
FILL = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.button).parameters
    else {"use_container_width": True}
)

PR_PROMPT = "Generate purchase requisition from UI form pre-seeded fields."

SUGGESTIONS = [
    "Create a purchase requisition for 50 laptops for IT",
    "Show the details of a material request",
    "Convert a purchase requisition to a draft purchase order",
]

st.set_page_config(
    page_title="ERPNext AI Procurement Console",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",   # drawer hidden by default
)

# =====================================================================
# DESIGN SYSTEM STYLESHEET
# ---------------------------------------------------------------------
# HOW TO READ THIS CSS:
#   • Section 1 lists every COLOR as a named token with a plain-English
#     description of WHERE it appears on screen.
#   • Sections 2+ are grouped by visual component, in the order the user
#     sees them (shell → sidebar → header → messages → drawer → responsive).
#   • To retheme, edit ONLY the color tokens in Section 1.
# =====================================================================
BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* =====================================================================
   SECTION 0 — FORCE STREAMLIT THEME (fixes all dark-theme bleed-through)
   =====================================================================
   Streamlit injects its own --background-color / --text-color CSS vars
   from config.toml. If the app is set to base="dark", those leak into
   components we didn't explicitly override (chat input frame, buttons,
   sidebar toggle, suggestion chips). We override them here so the whole
   app is deterministic and no white-on-white / black-on-black can occur.
   --------------------------------------------------------------------- */
:root,
[data-testid="stAppViewContainer"],
.stApp {
    --background-color: #F7F8FB !important;
    --secondary-background-color: #FFFFFF !important;
    --text-color: #0F172A !important;
    --primary-color: #4F46E5 !important;
    --font: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif !important;
}

/* =====================================================================
   SECTION 1 — COLOR TOKENS
   ===================================================================== */
:root{
    /* Surfaces */
    --canvas: #F7F8FB;
    --card: #FFFFFF;
    --thread-bg: #F7F8FB;

    /* Borders */
    --line: #E6E8EE;
    --line-soft: #EFF1F5;

    /* Text */
    --ink: #0F172A;
    --ink-on-accent: #FFFFFF;   /* NEW: text that sits on accent-tinted bg */
    --muted: #64748B;
    --muted-2: #94A3B8;         /* NEW: promoted from hardcoded chip gray */

    /* Brand */
    --accent: #4F46E5;
    --accent-2: #7C3AED;
    --accent-3: #DB2777;
    --accent-soft: #EEF0FF;
    --accent-line: #C7D2FE;
    --accent-hover: #4338CA;    /* NEW: darker indigo for hover states */
    --accent-hover-soft: #E0E5FF; /* NEW: hover tint for soft buttons */

    /* Success */
    --ok: #047857;
    --ok-soft: #ECFDF5;
    --ok-line: #A7F3D0;

    /* Error */
    --bad: #B91C1C;
    --bad-soft: #FEF2F2;
    --bad-line: #FECACA;
    --bad-ink: #7F1D1D;

    /* Shadows */
    --shadow-sm: 0 1px 2px rgba(15,23,42,.05);
    --shadow-md: 0 6px 24px rgba(15,23,42,.06);

    /* Shapes */
    --r: 14px;
    --r-sm: 10px;
    --drawer: 400px;
}

/* =====================================================================
   SECTION 2 — GLOBAL LAYOUT & CENTERED SHELL
   ===================================================================== */
html, body, [class*="css"]{
    font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    -webkit-font-smoothing:antialiased;
}

.stApp{
    color:var(--ink) !important;
    background:
        radial-gradient(900px 500px at 8% -10%, rgba(79,70,229,.06), transparent 60%),
        radial-gradient(900px 500px at 108% 4%, rgba(124,58,237,.05), transparent 60%),
        var(--canvas) !important;
}

[data-testid="stMainBlockContainer"],
[data-testid="stMain"] .block-container,
[data-testid="stBottomBlockContainer"]{
    max-width:820px;
    width:100%;
    margin-inline:auto;
    padding-inline:clamp(.75rem,3vw,1.5rem);
}

[data-testid="stMainBlockContainer"],
[data-testid="stMain"] .block-container{
    padding-top:1.75rem;
    padding-bottom:6rem;
}

[data-testid="stMain"]{
    transition:padding-right .25s ease;
    background:transparent !important;
}

/* =====================================================================
   SECTION 3 — HEADER
   ===================================================================== */
.app-title{
    background:linear-gradient(90deg,
        var(--accent) 0%, var(--accent-2) 70%, var(--accent-3) 100%);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    background-clip:text;
    font-weight:800;
    font-size:1.75rem;
    letter-spacing:-.02em;
    margin:0;
    line-height:1.15;
}
.app-sub{ color:var(--muted); font-size:.875rem; margin:2px 0 0; }
.side-title{ font-weight:700; font-size:1.02rem; margin:0 0 .35rem; color:var(--ink); }

/* =====================================================================
   SECTION 4 — STATUS PILL
   ===================================================================== */
.pill{
    display:inline-flex; align-items:center; gap:7px;
    padding:5px 12px; border-radius:999px;
    font-size:.72rem; font-weight:700;
    letter-spacing:.06em; text-transform:uppercase;
    border:1px solid transparent;
}
.pill::before{
    content:""; width:7px; height:7px;
    border-radius:50%; background:currentColor;
}
.pill.ready{ background:var(--ok-soft); color:var(--ok); border-color:var(--ok-line); }
.pill.ready::before{ animation:pulse-dot 1.8s infinite; }
.pill.busy{ background:var(--accent-soft); color:var(--accent); border-color:var(--accent-line); }
.pill.pending_approval{ background:var(--accent-soft); color:var(--accent); border-color:var(--accent-line); }
.pill.err{ background:var(--bad-soft); color:var(--bad); border-color:var(--bad-line); }

@keyframes pulse-dot{
    0%  {box-shadow:0 0 0 0    rgba(4,120,87,.55)}
    70% {box-shadow:0 0 0 8px  rgba(4,120,87,0)}
    100%{box-shadow:0 0 0 0    rgba(4,120,87,0)}
}

/* =====================================================================
   SECTION 5 — SIDEBAR  (fixes issue #5 — invisible toggle)
   ===================================================================== */
section[data-testid="stSidebar"]{
    background:var(--card) !important;
    border-right:1px solid var(--line);
}
section[data-testid="stSidebar"] *{
    color:var(--ink);
}
section[data-testid="stSidebar"] .block-container{
    padding-top:1.1rem;
}

.thread-box{
    background:var(--thread-bg);
    border:1px solid var(--line);
    color:var(--muted);
    padding:8px 10px;
    border-radius:8px;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:.72rem;
    word-break:break-all;
}

/* Sidebar collapse / expand controls — force visible icon color */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapsedControl"] a {
    color:var(--ink) !important;
    background:var(--card) !important;
    border:1px solid var(--line) !important;
    border-radius:8px !important;
}
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarCollapsedControl"] button:hover {
    background:var(--accent-soft) !important;
    color:var(--accent) !important;
    border-color:var(--accent-line) !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
    fill:currentColor !important;
    color:inherit !important;
}

/* =====================================================================
   SECTION 6 — CHAT MESSAGES  (fixes issue #1 — white-on-white)
   =====================================================================
   The key fix: we no longer rely on --card for BOTH the app canvas and
   the bubble. We give the assistant bubble a distinct card surface AND
   explicitly force its text color so Streamlit's dark-theme text can't
   bleed through.
   --------------------------------------------------------------------- */
[data-testid="stChatMessage"]{
    background:var(--card) !important;
    border:1px solid var(--line-soft) !important;
    color:var(--ink) !important;
    border-radius:var(--r);
    padding:.85rem 1.05rem;
    box-shadow:var(--shadow-sm);
    margin-bottom:.5rem;
}
/* Force every descendant (p, span, li, code, etc.) to ink so nothing inherits white */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] div,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] em {
    color:var(--ink) !important;
}
[data-testid="stChatMessage"] a { color:var(--accent) !important; }
[data-testid="stChatMessage"] code {
    background:var(--thread-bg) !important;
    color:var(--ink) !important;
    border:1px solid var(--line-soft);
    border-radius:6px;
    padding:1px 5px;
}

/* User bubble — accent tint, but STILL dark ink text so it's readable */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]){
    background:var(--accent-soft) !important;
    border-color:var(--accent-line) !important;
    color:var(--ink) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) span,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) div {
    color:var(--ink) !important;
}

/* =====================================================================
   SECTION 7 — CHAT INPUT COMPOSER (clean AI-tool style)
   =====================================================================
   Design goals:
     • One rounded container holds the textarea + send button.
     • No border on the textarea itself (the container owns the border).
     • Placeholder is muted, real text is ink.
     • Focus = indigo border + soft halo (no black anywhere).
     • Send button is a small circular indigo button inside the bar.
   --------------------------------------------------------------------- */

/* Outer wrappers — strip all backgrounds so nothing dark frames the bar */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div,
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* Constrain + center the composer to match the chat column width */
[data-testid="stBottomBlockContainer"],
[data-testid="stChatInput"] {
    max-width: 820px;
    width: 100%;
    margin-inline: auto;
    padding-inline: clamp(.75rem, 3vw, 1.5rem);
}

/* The composer bar itself — one clean rounded container */
[data-testid="stChatInput"] > div > div {
    background: var(--card) !important;
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    box-shadow: 0 4px 20px rgba(15, 23, 42, .06) !important;
    padding: 6px 8px 6px 14px !important;
    display: flex !important;
    align-items: flex-end !important;
    gap: 8px !important;
    transition: border-color .15s ease, box-shadow .15s ease;
}

/* Focused state — indigo border + soft halo, matching the app accent */
[data-testid="stChatInput"]:focus-within > div > div {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 4px rgba(79, 70, 229, .12),
                0 4px 20px rgba(15, 23, 42, .06) !important;
}

/* The actual textarea — no border, no bg, no shadow. Pure text surface. */
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input {
    background: transparent !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    color: var(--ink) !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    font-size: .95rem !important;
    line-height: 1.5 !important;
    padding: 10px 4px !important;
    resize: none !important;
    min-height: 24px !important;
    max-height: 200px !important;
}

/* Placeholder text — muted, fully opaque so it never disappears */
[data-testid="stChatInput"] textarea::placeholder,
[data-testid="stChatInput"] input::placeholder {
    color: var(--muted) !important;
    opacity: 1 !important;
}

/* Kill any residual background Streamlit paints inside the composer */
[data-testid="stChatInput"] * {
    background-color: transparent;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input {
    background-color: transparent !important;
}

/* Send button — small circular indigo button on the right */
[data-testid="stChatInput"] button {
    background: var(--accent) !important;
    color: var(--ink-on-accent) !important;
    border: none !important;
    border-radius: 50% !important;
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    padding: 0 !important;
    margin: 0 2px 2px 0 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    transition: background .15s ease, transform .12s ease;
    flex-shrink: 0 !important;
}

/* Send button hover — darker indigo, tiny lift */
[data-testid="stChatInput"] button:hover {
    background: var(--accent-hover) !important;
    transform: translateY(-1px);
}

/* Send button active — subtle press */
[data-testid="stChatInput"] button:active {
    transform: scale(.94);
}

/* Send button icon — force white so it's visible on indigo */
[data-testid="stChatInput"] button svg {
    fill: var(--ink-on-accent) !important;
    color: var(--ink-on-accent) !important;
    width: 16px !important;
    height: 16px !important;
}

/* Disabled send button (empty input) — muted, non-clickable look */
[data-testid="stChatInput"] button:disabled,
[data-testid="stChatInput"] button[disabled] {
    background: var(--line) !important;
    cursor: not-allowed !important;
    opacity: .6 !important;
}
[data-testid="stChatInput"] button:disabled svg,
[data-testid="stChatInput"] button[disabled] svg {
    fill: var(--muted) !important;
    color: var(--muted) !important;
}

/* =====================================================================
   SECTION 8 — BUTTONS  (fixes issues #3 and #4 — invisible chips + black hover)
   =====================================================================
   Explicitly set bg + text for ALL button states so Streamlit's dark
   theme can never paint black-on-black. Hover uses indigo (not black).
   --------------------------------------------------------------------- */
.stButton > button,
.stFormSubmitButton > button {
    background:var(--card) !important;
    color:var(--ink) !important;
    border:1px solid var(--line) !important;
    border-radius:var(--r-sm);
    font-weight:600;
    transition:transform .12s ease, box-shadow .12s ease,
               background .15s ease, color .15s ease, border-color .15s ease;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background:var(--accent-soft) !important;   /* indigo tint, NOT black */
    color:var(--accent-hover) !important;
    border-color:var(--accent-line) !important;
    box-shadow:var(--shadow-sm);
    transform:translateY(-1px);
}
.stButton > button:active,
.stFormSubmitButton > button:active {
    background:var(--accent-hover-soft) !important;
    color:var(--accent-hover) !important;
    transform:scale(.98);
}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
    outline:2px solid var(--accent);
    outline-offset:2px;
}
/* Primary buttons: solid indigo, white text */
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background:var(--accent) !important;
    color:var(--ink-on-accent) !important;
    border-color:var(--accent) !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background:var(--accent-hover) !important;
    color:var(--ink-on-accent) !important;
    border-color:var(--accent-hover) !important;
}
/* Force button labels to follow the button's color (Streamlit nests <p>) */
.stButton > button p,
.stFormSubmitButton > button p {
    color:inherit !important;
    margin:0;
}

/* =====================================================================
   SECTION 9 — THINKING INDICATOR
   ===================================================================== */
.think{
    display:flex; align-items:center; gap:.65rem;
    color:var(--muted); font-size:.9rem; font-weight:500;
}
.orb{
    width:14px; height:14px; border-radius:50%;
    background:var(--accent);
    animation:pulse-orb 1.4s ease-in-out infinite;
    flex-shrink:0;
}
@keyframes pulse-orb{
    0%,100%{box-shadow:0 0 0 0    rgba(79,70,229,.45); transform:scale(.9)}
    50%    {box-shadow:0 0 0 10px rgba(79,70,229,0);   transform:scale(1)}
}
.dots i{
    display:inline-block; width:4px; height:4px;
    margin-left:3px; border-radius:50%;
    background:var(--muted); animation:blink 1.2s infinite;
}
.dots i:nth-child(2){animation-delay:.2s}
.dots i:nth-child(3){animation-delay:.4s}
@keyframes blink{
    0%,80%,100%{opacity:.25}
    40%        {opacity:1}
}
.steps{
    display:flex;
    gap:.4rem;
    margin-top:.6rem;
    margin-bottom:.60rem;   /* NEW: breathing room below the chips row */
    flex-wrap:wrap;
}
.step{
    font-size:.72rem; padding:3px 11px;
    border-radius:999px;
    border:1px solid var(--line);
    color:var(--muted-2);
    background:var(--card);
    transition:all .3s ease;
    font-weight:500;
}
.step.on{
    border-color:var(--accent);
    color:var(--accent);
    background:var(--accent-soft);
}
.step.done{
    color:var(--ok);
    border-color:var(--ok-line);
    background:var(--ok-soft);
}

/* =====================================================================
   SECTION 10 — META FOOTER & ERROR BOX
   ===================================================================== */
/* =====================================================================
   SECTION 10 — META FOOTER (Completed-in badge)
   ===================================================================== */

/* Make the assistant bubble a flex column so the meta chip can be
   pushed to the bottom-right without affecting the message body. */
/* Kill Streamlit's default paragraph + container margins inside
   assistant bubbles so the badge sits snug under the response. */
/* Restore comfortable spacing between the avatar and the message content */
[data-testid="stChatMessage"] {
    gap: .75rem !important;              /* avatar ↔ content gap (was 0) */
    align-items: flex-start !important;
}

/* Kill the dead space ONLY between the body text and the badge,
   not between the avatar and the content column. */
[data-testid="stChatMessage"] [data-testid="stVerticalBlock"] {
    gap: .25rem !important;              /* was 0 — small breathing room */
}

/* Collapse the last paragraph's bottom margin so the badge sits close */
[data-testid="stChatMessage"] p:last-child {
    margin-bottom: 0 !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
}

/* The badge itself */
  .meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      align-self: flex-end;
-     margin-top: .75rem;
+     margin-top: .35rem;
      padding: 5px 12px;
      border-radius: 999px;
      border: 1px solid var(--ok-line);
      background: var(--ok-soft);
      color: var(--ok);
      font-size: .74rem;
      font-weight: 600;
      letter-spacing: .01em;
      line-height: 1;
      white-space: nowrap;
      box-shadow: 0 1px 2px rgba(4, 120, 87, .06);
      transition: background .15s ease, border-color .15s ease;
}

.meta:hover {
    background: #DCFCE7;
    border-color: #6EE7B7;
}

/* Tabular numerals so the time doesn't jitter between renders */
.meta {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
}

.err-box{
    background:var(--bad-soft);
    border:1px solid var(--bad-line);
    color:var(--bad-ink);
    border-radius:var(--r-sm);
    padding:.7rem .9rem;
    font-size:.88rem;
    margin-top:.5rem;
    line-height:1.5;
}

/* =====================================================================
   SECTION 11 — EMPTY STATE  (fixes issue #3 — invisible suggestions)
   =====================================================================
   The suggestions are rendered as stButton elements. With Section 8
   forcing white bg + ink text, they're now visible. We additionally
   ensure the empty-state text itself is legible.
   --------------------------------------------------------------------- */
.empty{ text-align:center; padding:3rem 0 1.5rem; }
.empty .icon{ font-size:2.25rem; margin-bottom:.5rem; }
.empty h3{
    color:var(--ink) !important;
    font-weight:700; font-size:1.15rem; margin:0 0 .35rem;
}
.empty p{
    color:var(--muted) !important;
    font-size:.92rem; margin:0;
}

/* =====================================================================
   SECTION 12 — MANUAL PR DRAWER
   ===================================================================== */
.st-key-pr_drawer{
    position:fixed; top:0; right:0;
    height:100vh;
    width:min(var(--drawer),100vw);
    z-index:1000;
    background:var(--card) !important;
    border-left:1px solid var(--line);
    box-shadow:-8px 0 24px rgba(15,23,42,.08);
    padding:1.25rem 1.35rem 2rem;
    overflow-y:auto;
    transform:translateX(105%);
    visibility:hidden;
    transition:transform .28s cubic-bezier(.22,.61,.36,1),
               visibility .28s;
    color:var(--ink);
}
.st-key-pr_drawer h4{ margin-top:.25rem; font-weight:700; color:var(--ink); }
.st-key-pr_drawer .stFormSubmitButton>button{ margin-top:.25rem; }

/* =====================================================================
   SECTION 13 — RESPONSIVE & ACCESSIBILITY
   ===================================================================== */
@media (prefers-reduced-motion: reduce){
    *{ animation:none !important; transition:none !important; }
}
@media (max-width: 640px){
    .app-title{ font-size:1.4rem; }
    [data-testid="stMainBlockContainer"],
    [data-testid="stMain"] .block-container{
        padding-top:1rem;
        padding-bottom:5rem;
    }
    .st-key-pr_drawer{ width:100vw; border-left:none; }
}

/* =====================================================================
   SECTION 14 — STREAMLIT HEADER (match app brand)
   =====================================================================
   The default stHeader is a separate white bar with gray text that
   visually detaches from the canvas. We blend it into the app by:
     • Making its background transparent (canvas shows through).
     • Removing its bottom border/shadow.
     • Tinting the sidebar toggle + menu icons in the brand ink color.
     • Restyling the "Deploy" button as a soft indigo pill.
     • Giving everything an indigo hover state (no black anywhere).
   --------------------------------------------------------------------- */

/* --- Header bar itself: transparent so it merges with the canvas --- */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    height: 3rem !important;
}

/* Remove any inner wrapper that Streamlit paints white */
header[data-testid="stHeader"] > div,
header[data-testid="stHeader"] > div > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* --- Sidebar toggle (the » chevron on the left) --- */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapsedControl"] a,
header[data-testid="stHeader"] button[kind="header"] {
    background: transparent !important;
    color: var(--muted) !important;
    border: none !important;
    border-radius: 8px !important;
    transition: background .15s ease, color .15s ease;
}
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="stSidebarCollapsedControl"] a:hover,
header[data-testid="stHeader"] button[kind="header"]:hover {
    background: var(--accent-soft) !important;
    color: var(--accent) !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg,
header[data-testid="stHeader"] button[kind="header"] svg {
    fill: currentColor !important;
    color: inherit !important;
}

/* --- "Deploy" button: soft indigo pill instead of plain gray text --- */
[data-testid="stAppDeployButton"],
[data-testid="stDeployButton"],
header[data-testid="stHeader"] [data-testid="stBaseButton-header"] {
    background: var(--accent-soft) !important;
    color: var(--accent) !important;
    border: 1px solid var(--accent-line) !important;
    border-radius: 999px !important;
    font-weight: 600 !important;
    font-size: .8rem !important;
    padding: 4px 14px !important;
    height: auto !important;
    transition: background .15s ease, color .15s ease, border-color .15s ease;
}
[data-testid="stAppDeployButton"]:hover,
[data-testid="stDeployButton"]:hover,
header[data-testid="stHeader"] [data-testid="stBaseButton-header"]:hover {
    background: var(--accent) !important;
    color: var(--ink-on-accent) !important;
    border-color: var(--accent) !important;
}
/* Force inner label to follow button color */
[data-testid="stAppDeployButton"] *,
[data-testid="stDeployButton"] *,
header[data-testid="stHeader"] [data-testid="stBaseButton-header"] * {
    color: inherit !important;
}

/* --- Overflow / ⋮ menu button on the far right --- */
[data-testid="stMainMenu"],
header[data-testid="stHeader"] [data-testid="stMainMenu"] button {
    background: transparent !important;
    color: var(--muted) !important;
    border: none !important;
    border-radius: 8px !important;
    transition: background .15s ease, color .15s ease;
}
[data-testid="stMainMenu"]:hover,
header[data-testid="stHeader"] [data-testid="stMainMenu"] button:hover {
    background: var(--accent-soft) !important;
    color: var(--accent) !important;
}
[data-testid="stMainMenu"] svg,
header[data-testid="stHeader"] [data-testid="stMainMenu"] svg {
    fill: currentColor !important;
    color: inherit !important;
}

/* --- Running indicator ("Running…" man walking) — tint to brand --- */
[data-testid="stStatusWidget"] {
    color: var(--accent) !important;
    background: transparent !important;
}
[data-testid="stStatusWidget"] svg {
    fill: var(--accent) !important;
    color: var(--accent) !important;
}

/* --- The ⋮ dropdown popover, once opened --- */
[data-testid="stMainMenuPopover"],
div[data-testid="stMainMenuPopover"] ul {
    background: var(--card) !important;
    border: 1px solid var(--line) !important;
    border-radius: var(--r-sm) !important;
    box-shadow: var(--shadow-md) !important;
}
[data-testid="stMainMenuPopover"] li,
[data-testid="stMainMenuPopover"] a,
[data-testid="stMainMenuPopover"] span {
    color: var(--ink) !important;
}
[data-testid="stMainMenuPopover"] li:hover {
    background: var(--accent-soft) !important;
    color: var(--accent) !important;
}

/* --- Small screens: keep it clean --- */
@media (max-width: 640px) {
    header[data-testid="stHeader"] { height: 2.6rem !important; }
    [data-testid="stAppDeployButton"] { display: none !important; }
}

/* =====================================================================
   SECTION 15 — LINE ITEM CARDS (replaces st.data_editor)
   ===================================================================== */

/* Section heading inside the drawer */
.li-header {
    font-weight: 700;
    font-size: .92rem;
    color: var(--ink);
    margin: 1rem 0 .5rem;
}

/* Each line-item card */
[class*="st-key-li_row_"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    padding: .85rem 1rem 1rem;
    margin-bottom: .65rem;
    transition: border-color .15s ease, box-shadow .15s ease;
}
[class*="st-key-li_row_"]:hover {
    border-color: var(--accent-line);
    box-shadow: var(--shadow-sm);
}

/* "Item N" title inside each card */
.li-title {
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: .4rem;
}

/* Tighten label + input spacing inside the drawer */
.st-key-pr_drawer label,
[class*="st-key-li_row_"] label {
    font-size: .78rem !important;
    font-weight: 600 !important;
    color: var(--muted) !important;
    margin-bottom: .15rem !important;
}

/* Cleaner text inputs / number inputs inside the drawer */
.st-key-pr_drawer input,
.st-key-pr_drawer textarea,
.st-key-pr_drawer [data-baseweb="select"] > div,
[class*="st-key-li_row_"] input,
[class*="st-key-li_row_"] [data-baseweb="select"] > div {
    background: var(--card) !important;
    color: var(--ink) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px !important;
    font-size: .9rem !important;
}
.st-key-pr_drawer input:focus,
.st-key-pr_drawer textarea:focus,
[class*="st-key-li_row_"] input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, .12) !important;
    outline: none !important;
}

/* Remove-button alignment (sits next to qty/rate) */
.li-remove-spacer { height: 1.55rem; }         /* aligns with input label height */
[class*="st-key-li_row_"] .stButton > button {
    height: 2.5rem !important;
    padding: 0 10px !important;
}

/* "+ Add line item" — dashed outline, indigo on hover */
.st-key-li_add .stButton > button,
button[kind="secondary"][data-testid*="li_add"] {
    background: transparent !important;
    color: var(--accent) !important;
    border: 1.5px dashed var(--accent-line) !important;
    border-radius: var(--r-sm) !important;
    font-weight: 600 !important;
    padding: .55rem 1rem !important;
    width: 100% !important;
    transition: all .15s ease;
}
.st-key-li_add .stButton > button:hover,
button[kind="secondary"][data-testid*="li_add"]:hover {
    background: var(--accent-soft) !important;
    border-color: var(--accent) !important;
}
</style>
"""
st.markdown(BASE_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Session state — single source of truth
# ---------------------------------------------------------------------
ss = st.session_state
ss.setdefault("erpnext_auth_cookie", None)
ss.setdefault("thread_id", f"st_session_{uuid.uuid4()}")
ss.setdefault("messages", [])
ss.setdefault("user_id", None)
ss.setdefault("pr_open", False)
ss.setdefault("pending", None)       # one queue for chat, chips, form, retry
ss.setdefault("last_request", None)
ss.setdefault("health", "ready")     # ready | busy | err
ss.setdefault("approval_pending", False)
ss.setdefault("approval_payload", None)
ss.setdefault("approval_error", None)


def initiate_fresh_session() -> None:
    ss.thread_id = f"st_session_{uuid.uuid4()}"
    ss.messages, ss.pending, ss.last_request, ss.health = [], None, None, "ready"
    ss.approval_pending, ss.approval_payload, ss.approval_error = False, None, None


def set_pr_panel(is_open: bool) -> None:
    ss.pr_open = is_open


def ask(query: str, form: Optional[dict] = None, display: Optional[str] = None) -> None:
    ss.pending = {"query": query, "form": form, "display": display or query, "echo": True}


def retry_last() -> None:
    if ss.last_request:
        if ss.messages and ss.messages[-1].get("error"):
            ss.messages.pop()
        ss.pending = {**ss.last_request, "echo": False}


def pill_html(state: str) -> str:
    label = {
        "ready": "Ready",
        "busy": "Processing",
        "pending_approval": "Review required",
        "err": "Needs attention",
    }[state]
    return f'<span class="pill {state}">{label}</span>'


if not ss.erpnext_auth_cookie:
    render_login_page()
    st.stop()


# ---------------------------------------------------------------------
# Sidebar — vertical navigation + session controls
# ---------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="side-title">🤖 Intelligent Procurement Hub</div>', unsafe_allow_html=True)
    pill_slot = st.empty()
    pill_slot.markdown(pill_html(ss.health), unsafe_allow_html=True)
    st.write("")

    if ss.erpnext_auth_cookie:
        st.success("ERPNext session connected")
        if st.button("Log out", **FILL):
            clear_authentication()
            initiate_fresh_session()
            st.rerun()

    st.button(
        "💬  Chat assistant", **FILL,
        type="secondary" if ss.pr_open else "primary",
        on_click=set_pr_panel, args=(False,),
    )
    st.button(
        "📝  Manual PR entry", **FILL,
        type="primary" if ss.pr_open else "secondary",
        on_click=set_pr_panel, args=(not ss.pr_open,),
    )

    st.divider()
    st.markdown("**Active thread**")
    st.markdown(f'<div class="thread-box">{ss.thread_id}</div>', unsafe_allow_html=True)
    st.write("")
    if st.button("🔄  New session", disabled=ss.approval_pending, **FILL):
        initiate_fresh_session()
        st.rerun()
    if ss.approval_pending:
        st.caption("Resolve the pending purchase-order review before starting a new session.")

# ---------------------------------------------------------------------
# Manual PR drawer (always rendered so entered data survives open/close)
# ---------------------------------------------------------------------
def to_number(value) -> Optional[float]:
    try:
        num = float(value)
        return num if num == num else None
    except (TypeError, ValueError):
        return None


def validate_pr(company: str, title: str, txn: date, sched: date, rows) -> Tuple[list, list]:
    errors, items = [], []
    if not company.strip():
        errors.append("Company name is required.")
    if not title.strip():
        errors.append("Requisition title is required.")
    if sched < txn:
        errors.append("Delivery date can't be earlier than the transaction date.")
    for i, row in enumerate(rows, 1):
        code = str(row.get("item_code") or "").strip()
        if not code or code.lower() == "nan":
            continue
        qty, rate = to_number(row.get("qty")), to_number(row.get("rate"))
        if qty is None or qty <= 0:
            errors.append(f"Line {i}: quantity must be greater than 0.")
        elif rate is None or rate < 0:
            errors.append(f"Line {i}: rate can't be negative.")
        else:
            items.append({
                "item_code": code, "qty": qty, "uom": row.get("uom") or "Nos",
                "rate": rate, "schedule_date": sched.strftime("%Y-%m-%d"),
            })
    if not items and not any("Line" in e for e in errors):
        errors.append("Add at least one line item with an item code.")
    return errors, items


with st.container(key="pr_drawer"):
    head, close = st.columns([5, 1], vertical_alignment="center")
    with head:
        st.markdown("#### 📝 Purchase requisition")
        st.caption("Manual entry. Submitted through the same agent workflow as chat.")
    with close:
        st.button("✕", key="close_pr", help="Close panel",
                  on_click=set_pr_panel, args=(False,))

    with st.form("pr_intake_form", clear_on_submit=False):
        form_company = st.text_input("Company name", value="Maahi's Foundation")
        form_dept = st.selectbox("Department", DEPARTMENTS)
        form_title = st.text_input("Requisition title",
                                   placeholder="e.g., Urgent team request")
        form_remark = st.text_area("Remarks / justification",
                                   placeholder="Why is this needed?", height=80)

        c1, c2 = st.columns(2)
        form_txn = c1.date_input("Transaction date", value=date.today())
        form_sched = c2.date_input("Delivery date", value=date.today())

        st.markdown('<div class="li-header">Line items</div>', unsafe_allow_html=True)

        # Session-backed list of line items so add/remove survives reruns
        ss.setdefault("pr_items", [{"item_code": "ITEM-001", "qty": 100, "uom": "Nos", "rate": 100.0}])

        # --- Render each line item as a clean card ---
        for i, item in enumerate(ss.pr_items):
            with st.container(key=f"li_row_{i}"):
                st.markdown(
                    f'<div class="li-title">Item {i + 1}</div>',
                    unsafe_allow_html=True,
                )

                # Row 1: code + UoM
                c1, c2 = st.columns([3, 1])
                item["item_code"] = c1.text_input(
                    "Item code",
                    value=item.get("item_code", ""),
                    key=f"li_code_{i}",
                    placeholder="e.g., ITEM-001",
                    label_visibility="visible",
                )
                item["uom"] = c2.selectbox(
                    "UoM",
                    options=UOMS,
                    index=UOMS.index(item.get("uom", "Nos")) if item.get("uom") in UOMS else 0,
                    key=f"li_uom_{i}",
                )

                # Row 2: qty + rate + remove
                c3, c4, c5 = st.columns([2, 2, 1])
                item["qty"] = c3.number_input(
                    "Quantity",
                    min_value=1.0,
                    step=1.0,
                    value=float(item.get("qty", 1)),
                    key=f"li_qty_{i}",
                )
                item["rate"] = c4.number_input(
                    "Rate",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    value=float(item.get("rate", 0.0)),
                    key=f"li_rate_{i}",
                )
                c5.markdown('<div class="li-remove-spacer"></div>', unsafe_allow_html=True)
                if c5.form_submit_button("✕", key=f"li_del_{i}", help="Remove this line"):
                    ss.pr_items.pop(i)
                    st.rerun()

        # --- Add line item ---
        if st.form_submit_button("+ Add line item", key="li_add", **FILL):
            ss.pr_items.append({"item_code": "", "qty": 1.0, "uom": "Nos", "rate": 0.0})
            st.rerun()

        submit_form = st.form_submit_button("Verify & generate PR", **FILL, type="primary")

    if submit_form:
        rows = list(ss.pr_items)
        form_errors, items = validate_pr(form_company, form_title, form_txn, form_sched, rows)
        if form_errors:
            for msg in form_errors:
                st.error(msg, icon="⚠️")
        else:
            doc = {
                "company": form_company.strip(),
                "department": form_dept,
                "title": form_title.strip(),
                "remark": form_remark,
                "transaction_date": form_txn.strftime("%Y-%m-%d"),
                "schedule_date": form_sched.strftime("%Y-%m-%d"),
                "items": items,
            }
            lines = "\n".join(
                f"- {i['item_code']} × {i['qty']:g} {i['uom']} @ {i['rate']:g}"
                for i in items
            )
            ask(PR_PROMPT, form=doc, display=(
                f"**Submitting purchase requisition**\n\n"
                f"- **Company:** {doc['company']}\n"
                f"- **Department:** {doc['department']}\n"
                f"- **Title:** {doc['title']}\n{lines}"
            ))
            ss.pr_items = [{"item_code": "ITEM-001", "qty": 100, "uom": "Nos", "rate": 100.0}]
            ss.pr_open = False   # return focus to chat; form values kept

# Drawer visibility decided AFTER form handling (reflects this run's state)

if ss.pr_open:
    st.markdown(
        """<style>
        .st-key-pr_drawer{transform:none!important;visibility:visible!important}
        @media (min-width:1200px){[data-testid="stMain"]{padding-right:var(--drawer)}}
        </style>""",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------
left, right = st.columns([4, 2], vertical_alignment="center")
with left:
    st.markdown(
        '<p class="app-title">ERPNext AI Procurement Console</p>'
        '<p class="app-sub">Intelligent Procurement Automation—From Draft To Submission, Tracking & Conversion.</p>',
        unsafe_allow_html=True,
    )
with right:
    st.button(
        "📝  New requisition", key="open_pr_top", **FILL,
        on_click=set_pr_panel, args=(True,),
    )
st.divider()

# ---------------------------------------------------------------------
# Backend streaming — async SSE → queue → sync generator with heartbeat
# ---------------------------------------------------------------------
async def _stream_backend(
    payload: dict,
    queue: "asyncio.Queue[Tuple[str, Any]]",
    auth_cookie: str,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                FASTAPI_STREAM_URL,
                json=payload,
                headers={"Cookie": f"{AUTH_COOKIE_NAME}={auth_cookie}"},
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="ignore")[:300]
                    await queue.put(("error", f"Backend returned {response.status_code}. {body}"))
                    return
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw in ("", "[DONE]"):
                        continue
                    try:
                        frame = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    kind, content = frame.get("type"), frame.get("content", "")
                    if kind == "token":
                        await queue.put(("token", content))
                    elif kind == "error":
                        await queue.put(("error", str(content)))
                    elif kind == "approval_required" and isinstance(content, dict):
                        await queue.put(("approval", content))
                    elif kind in ("status", "tool", "tool_call", "node") and isinstance(content, str) and content:
                        await queue.put(("status", content))
    except httpx.TimeoutException:
        await queue.put(("error", "The request timed out. The agent may be busy; try again."))
    except httpx.RequestError as exc:
        await queue.put(("error",
                         f"Can't reach the procurement backend ({type(exc).__name__}). "
                         "Check that it is running on port 8001."))
    finally:
        await queue.put(("done", ""))


async def _new_queue() -> "asyncio.Queue[Tuple[str, Any]]":
    return asyncio.Queue()


def event_stream(payload: dict) -> Generator[Tuple[str, Any], None, None]:
    """Yields (kind, text): token | status | error | tick (heartbeat)."""
    loop = asyncio.new_event_loop()
    queue = loop.run_until_complete(_new_queue())
    task = loop.create_task(
        _stream_backend(payload, queue, ss.erpnext_auth_cookie)
    )
    try:
        while True:
            try:
                kind, text = loop.run_until_complete(asyncio.wait_for(queue.get(), 0.5))
            except asyncio.TimeoutError:
                yield ("tick", "")
                continue
            if kind == "done":
                break
            yield (kind, text)
    finally:
        task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        finally:
            loop.close()


# ---------------------------------------------------------------------
# Chat rendering helpers
# ---------------------------------------------------------------------
STAGES = ["Understanding", "Processing", "Responding"]


def think_html(stage: int, note: str) -> str:
    chips = "".join(
        f'<span class="step {"done" if i < stage else "on" if i == stage else ""}">'
        f'{"✓ " if i < stage else ""}{name}</span>'
        for i, name in enumerate(STAGES)
    )
    return (
        f'<div class="think"><span class="orb"></span><span>{note}</span>'
        f'<span class="dots"><i></i><i></i><i></i></span></div>'
        f'<div class="steps">{chips}</div>'
    )


def idle_note(elapsed: float) -> Tuple[int, str]:
    if elapsed < 2:
        return 0, "Understanding your request"
    if elapsed < 10:
        return 1, "Running the procurement workflow"
    return 1, "Still working — multi-step requests can take a moment"


def render_error(text: str) -> None:
    st.markdown(
        f'<div class="err-box"><b>Something went wrong.</b> {text}</div>',
        unsafe_allow_html=True,
    )


def run_turn(req: Dict) -> None:
    payload = {
        "query": req["query"],
        "thread_id": ss.thread_id,
        "user_id": ss.user_id,
        "metadata": {"interface": "streamlit_stream"},
    }
    if req.get("form"):
        payload["metadata"]["structured_doc"] = req["form"]

    ss.last_request, ss.health = req, "busy"
    pill_slot.markdown(pill_html("busy"), unsafe_allow_html=True)

    text, error, backend_note, stage, shown = "", None, None, 0, None
    approval = None
    start = time.perf_counter()    

    with st.chat_message("assistant", avatar="🤖"):
        status_ph, body_ph, foot_ph = st.empty(), st.empty(), st.empty()
        status_ph.markdown(think_html(0, "Understanding your request"), unsafe_allow_html=True)

        for kind, chunk in event_stream(payload):
            if kind == "token":
                text += chunk
                body_ph.markdown(text + " ▌")
                stage = 2
            elif kind == "status":
                backend_note, stage = chunk, max(stage, 1)
            elif kind == "approval":
                approval = chunk
                ss.approval_pending = True
                ss.approval_payload = chunk
                ss.approval_error = None
                text = (
                    f"Review required: **{chunk.get('action_label', 'purchase-order action')}**. "
                    "Please review the document details before continuing."
                )
                break
            elif kind == "error":
                error = chunk
                break

            if stage < 2:
                idle_stage, note = idle_note(time.time() - start)
                stage = max(stage, idle_stage)
                note = backend_note or note
            else:
                note = "Writing the response"

            if (stage, note) != shown:
                shown = (stage, note)
                status_ph.markdown(think_html(stage, note), unsafe_allow_html=True)

        elapsed = time.perf_counter() - start
        status_ph.empty()
        if text:
            body_ph.markdown(text)
        if not error and not text and approval is None:
            error = "The agent finished without returning a response."

        if approval is not None:
            meta = "⏸ Waiting for your review"
            foot_ph.markdown(f'<div class="meta">{meta}</div>', unsafe_allow_html=True)
            ss.health = "pending_approval"
            ss.messages.append({"role": "assistant", "content": text, "meta": meta})
        elif error:
            with foot_ph.container():
                render_error(error)
            ss.health = "err"
            ss.messages.append({"role": "assistant", "content": text, "error": error})
            st.button("↻ Retry", key=f"retry_{len(ss.messages)}", on_click=retry_last)
        else:
            meta = f"✓ Completed in {elapsed:.1f}s"
            foot_ph.markdown(f'<div class="meta">{meta}</div>', unsafe_allow_html=True)
            ss.health = "ready"
            ss.messages.append({"role": "assistant", "content": text, "meta": meta})

    pill_slot.markdown(pill_html(ss.health), unsafe_allow_html=True)
    if approval is not None:
        st.switch_page("pages/Approval.py")


# ---------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------
for idx, msg in enumerate(ss.messages):
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
        if msg["content"]:
            st.markdown(msg["content"])
        if msg.get("error"):
            render_error(msg["error"])
            if idx == len(ss.messages) - 1:
                st.button("↻ Retry", key=f"retry_{idx + 1}", on_click=retry_last)
        elif msg.get("meta"):
            st.markdown(f'<div class="meta">{msg["meta"]}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Empty state + suggestion chips
# ---------------------------------------------------------------------
welcome = st.empty()
if not ss.messages and not ss.pending:
    with welcome.container():
        st.markdown(
            '<div class="empty">'
            '<div class="icon">✨</div>'
            '<h3>What do you need to procure?</h3>'
            '<p>Create requisitions, review orders, or convert a PR to a purchase order.</p>'
            "</div>",
            unsafe_allow_html=True,
        )
        for i, suggestion in enumerate(SUGGESTIONS):
            st.button(suggestion, key=f"chip_{i}", **FILL, on_click=ask, args=(suggestion,))

# ---------------------------------------------------------------------
# Composer + dispatch (single pending queue drives every turn)
# ---------------------------------------------------------------------
if ss.approval_pending:
    st.warning("This conversation is paused until the purchase-order review is decided.")
    st.page_link("pages/Approval.py", label="Open pending review", icon="🔒")

if user_query := st.chat_input(
    "Ask about requisitions, orders, or approvals…",
    disabled=ss.approval_pending,
):
    ask(user_query)

if ss.pending:
    welcome.empty()
    req, ss.pending = ss.pending, None   # clear first so an interrupted run never replays
    if req.get("echo", True):
        ss.messages.append({"role": "user", "content": req["display"]})
        with st.chat_message("user", avatar="👤"):
            st.markdown(req["display"])
    run_turn(req)