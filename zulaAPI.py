# Drake Hooks + WaterTrooper
# Casino Claim 3
# Zula API (SeleniumBase UC; original login flow + candidate/state-based claim detection)
# Exposes: async def zula_uc(ctx, channel)

import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import discord
from dotenv import load_dotenv
from seleniumbase import SB

load_dotenv()

# Expect "email:password" in ZULA
ZULA_CRED = os.getenv("ZULA", "")

# ───────────────────────────────────────────────────────────
# State markers
# ───────────────────────────────────────────────────────────

CLAIMED_MARKERS = (
    "TODAY'S BONUS IS CLAIMED",
    "TODAYS BONUS IS CLAIMED",
    "TODAY’S BONUS IS CLAIMED",
    "BONUS IS CLAIMED",
    "DAILY BONUS CLAIMED",
    "ALREADY CLAIMED",
    "SEE YOU TOMORROW",
    "COME BACK TOMORROW",
)

# Zula's current successful-claim popup does not necessarily say "claimed".
# The popup shown after a real claim contains:
#   CONGRATULATIONS! / 10,000 / 1.00 / START PLAYING
# These markers are evaluated as combinations, not as single loose matches.
CLAIM_SUCCESS_TITLE_MARKERS = (
    "CONGRATULATIONS",
    "CONGRATS",
)

CLAIM_SUCCESS_ACTION_MARKERS = (
    "START PLAYING",
    "PLAY NOW",
    "CONTINUE",
)

CLAIM_SUCCESS_GENERIC_MARKERS = (
    "CLAIM SUCCESSFUL",
    "SUCCESSFULLY CLAIMED",
    "REWARD CLAIMED",
    "BONUS CLAIMED",
    "REWARD ADDED",
    "BONUS ADDED",
    "YOU RECEIVED",
    "YOU'VE RECEIVED",
)

CLAIM_SUCCESS_REWARD_MARKERS = (
    "10,000",
    "10000",
    "1.00",
    "GOLD COINS",
    "SWEEPS COINS",
)

CHECKOUT_MARKERS = (
    "CHECKOUT",
    "ORDER SUMMARY",
    "PAYMENT METHOD",
    "TOTAL AMOUNT TO PAY",
    "PAY $",
    "CREDIT/DEBIT",
    "PAY USING",
    "SKRILL",
)

REWARDS_MARKERS = (
    "COIN STORE",
    "CLAIM FREE REWARDS",
    "FREE REWARDS",
    "SPECIAL OFFERS",
)

BAD_CONTEXT_MARKERS = (
    "CHECKOUT",
    "ORDER SUMMARY",
    "PAYMENT METHOD",
    "TOTAL AMOUNT TO PAY",
    "CREDIT/DEBIT",
    "PAY USING",
    "SKRILL",
    "FACEBOOK CONNECT",
    "GOOGLE CONNECT",
)


# ───────────────────────────────────────────────────────────
# Text helpers
# ───────────────────────────────────────────────────────────

def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\xa0", " ").replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", value).strip()


def _up(value: Any) -> str:
    return _norm(value).upper()


def _contains_any(text: Any, markers: Tuple[str, ...]) -> bool:
    upper = _up(text)
    return any(marker in upper for marker in markers)


def _first_marker(text: Any, markers: Tuple[str, ...]) -> str:
    upper = _up(text)
    for marker in markers:
        if marker in upper:
            return marker
    return ""


def _short(text: Any, limit: int = 160) -> str:
    text = _norm(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_js(sb: SB, script: str, *args, default=None):
    try:
        return sb.execute_script(script, *args)
    except Exception as e:
        print(f"[Zula][JS WARN] {e}")
        return default


# ───────────────────────────────────────────────────────────
# Screenshot helpers
# ───────────────────────────────────────────────────────────

async def _send_post_claim(sb: SB, channel: discord.abc.Messageable, path: str, caption: str):
    """Only used on successful verified claim to avoid false-positive screenshot spam."""
    try:
        sb.save_screenshot(path)
        await channel.send(caption, file=discord.File(path))
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


async def _send_status_shot(sb: SB, channel: discord.abc.Messageable, caption: str, prefix: str):
    """
    One-off screenshot for unavailable, already-claimed, checkout, or error states.
    Creates a temp file, attaches it, and cleans up.
    """
    fd, tmp_path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".png", dir="/tmp")
    os.close(fd)

    try:
        sb.save_screenshot(tmp_path)
        await channel.send(caption, file=discord.File(tmp_path))
    except Exception:
        try:
            await channel.send(caption)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# ───────────────────────────────────────────────────────────
# Click helpers
# ───────────────────────────────────────────────────────────

def _force_click_xpath(sb: SB, xpath: str, timeout: float = 12) -> bool:
    """Robust click chain for stubborn elements."""
    try:
        sb.wait_for_element_visible(xpath, timeout=timeout)
    except Exception:
        return False

    try:
        sb.scroll_to(xpath)
    except Exception:
        pass

    for mode in ("click", "slow", "js", "directjs"):
        try:
            if mode == "click":
                sb.click_xpath(xpath, timeout=2)
            elif mode == "slow":
                sb.slow_click(xpath)
            elif mode == "js":
                sb.js_click(xpath)
            else:
                el = sb.find_element(xpath)
                sb.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue

    return False


def _try_click_any(sb: SB, xpaths, timeout_each=10) -> bool:
    for xp in xpaths:
        if xp and _force_click_xpath(sb, xp, timeout=timeout_each):
            return True
    return False


def _click_candidate(sb: SB, candidate_id: str) -> bool:
    """
    Clicks a JS-tagged candidate button by its temporary data-zula-candidate-id.
    This avoids brittle absolute claim XPaths.
    """
    if not candidate_id:
        return False

    selector = f"[data-zula-candidate-id='{candidate_id}']"

    try:
        sb.scroll_to(selector)
    except Exception:
        pass

    for mode in ("normal", "js", "dispatch"):
        try:
            if mode == "normal":
                sb.click(selector, timeout=2)
                return True

            if mode == "js":
                sb.js_click(selector)
                return True

            ok = _safe_js(
                sb,
                """
                const el = document.querySelector(arguments[0]);
                if (!el) return false;

                el.scrollIntoView({block: "center", inline: "center"});

                for (const type of ["mouseover", "mousedown", "mouseup", "click"]) {
                    el.dispatchEvent(new MouseEvent(type, {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }));
                }

                return true;
                """,
                selector,
                default=False,
            )

            if ok:
                return True

        except Exception:
            continue

    return False


# ───────────────────────────────────────────────────────────
# Original popup helpers
# ───────────────────────────────────────────────────────────

def _close_lobby_popups_flexible(sb: SB):
    """
    Close up to TWO popups that share the same close button XPath.
    Works if there are 0, 1, or 2 popups.
    Includes both /div[4]/... and /div[5]/... variants.
    """
    popup_close_xpaths = [
        "/html/body/div[4]/div/div[1]/div/div/button",
        "/html/body/div[5]/div/div[1]/div/div/button",
    ]

    closed = 0

    for _ in range(2):
        clicked_any = _try_click_any(sb, popup_close_xpaths, timeout_each=6)

        if clicked_any:
            closed += 1
            sb.wait(0.6)
        else:
            sb.wait(0.8)

            if _try_click_any(sb, popup_close_xpaths, timeout_each=3):
                closed += 1
                sb.wait(0.5)

    print(f"[Zula] Closed lobby popups: {closed} (0–2 expected)")


def _extra_popup_cleanup(sb: SB):
    """
    Extra cleanup for any additional popups that might obscure header buttons.
    """
    popup_xpaths = [
        "/html/body/div[4]/div/div[1]/div/div/button",
        "/html/body/div[5]/div/div[1]/div/div/button",
        "/html/body/div[6]/div/div[1]/div/div/button",
        "/html/body/div[4]/div/div/div[2]/button[4]",
        "/html/body/div[4]/div[4]/div/div/div/div[1]/div",
        "//button[contains(@class,'dialog-close-button')]",
        "//button[contains(@aria-label,'Close') or contains(@aria-label,'close')]",
        "//button[contains(translate(., 'CLOSE', 'close'),'close')]",
        "//button[contains(.,'Close')]",
        "//button[contains(.,'Accept All')]",
        "//button[contains(.,'Accept')]",
    ]

    for _ in range(2):
        if _try_click_any(sb, popup_xpaths, timeout_each=4):
            print("[Zula] Closed an extra popup.")
            sb.wait(0.3)

    try:
        sb.press_keys("body", "ESCAPE")
    except Exception:
        pass


# ───────────────────────────────────────────────────────────
# Page scan / state detection
# ───────────────────────────────────────────────────────────

def _page_text(sb: SB) -> str:
    """
    Broadly scans visible page text plus title/url.
    This is what catches:
    - TODAY'S BONUS IS CLAIMED
    - SEE YOU TOMORROW
    - CHECKOUT
    even when the element XPath changes.
    """
    data = _safe_js(
        sb,
        """
        const visible = (el) => {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== "none"
                && s.visibility !== "hidden"
                && s.opacity !== "0"
                && r.width > 0
                && r.height > 0;
        };

        const visibleText = Array.from(document.querySelectorAll("body *"))
            .filter(visible)
            .map((el) => [
                el.innerText || el.textContent || el.value || "",
                el.getAttribute("aria-label") || "",
                el.getAttribute("title") || "",
                el.getAttribute("role") || ""
            ].join(" "))
            .join(" ");

        return {
            url: window.location.href || "",
            title: document.title || "",
            body: document.body ? (document.body.innerText || document.body.textContent || "") : "",
            visibleText
        };
        """,
        default={},
    )

    if not isinstance(data, dict):
        return ""

    return _norm(
        " ".join(
            [
                data.get("url", ""),
                data.get("title", ""),
                data.get("body", ""),
                data.get("visibleText", ""),
            ]
        )
    )



def _visible_page_text(sb: SB) -> str:
    """
    Returns visible rendered text only.

    This is used for post-click success detection so hidden template text does
    not accidentally count as a successful claim.
    """
    value = _safe_js(
        sb,
        """
        if (!document.body) return "";
        return document.body.innerText || "";
        """,
        default="",
    )
    return _norm(value)


def _visible_modal_candidates(sb: SB) -> List[Dict[str, Any]]:
    """
    Scans visible dialogs/popups/modals and returns their text plus button text.

    Zula changes wrapper indexes often, so this intentionally avoids absolute
    modal XPaths. It also catches the successful "CONGRATULATIONS /
    START PLAYING" popup shown after the daily reward is collected.
    """
    result = _safe_js(
        sb,
        """
        const visible = (el) => {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== "none"
                && s.visibility !== "hidden"
                && s.opacity !== "0"
                && r.width > 0
                && r.height > 0;
        };

        const selectors = [
            "[role='dialog']",
            "[aria-modal='true']",
            "[class*='modal']",
            "[class*='Modal']",
            "[class*='dialog']",
            "[class*='Dialog']",
            "[class*='popup']",
            "[class*='Popup']"
        ];

        const seen = new Set();
        const out = [];

        for (const selector of selectors) {
            for (const el of Array.from(document.querySelectorAll(selector))) {
                if (!visible(el) || seen.has(el)) continue;

                const text = (el.innerText || el.textContent || "").trim();
                if (!text) continue;

                // Skip giant app/root containers accidentally matching a class.
                if (text.length > 4000) continue;

                seen.add(el);

                const buttons = Array.from(
                    el.querySelectorAll(
                        "button, [role='button'], a, input[type='button'], input[type='submit']"
                    )
                )
                    .filter(visible)
                    .map((btn) => (
                        btn.innerText
                        || btn.textContent
                        || btn.value
                        || btn.getAttribute("aria-label")
                        || btn.getAttribute("title")
                        || ""
                    ).trim())
                    .filter(Boolean);

                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                out.push({
                    text,
                    buttons,
                    role: el.getAttribute("role") || "",
                    ariaModal: el.getAttribute("aria-modal") || "",
                    classes: el.className ? String(el.className) : "",
                    position: style.position || "",
                    zIndex: style.zIndex || "",
                    area: Math.round(rect.width * rect.height)
                });
            }
        }

        return out;
        """,
        default=[],
    )

    return result if isinstance(result, list) else []


def _modal_signature(modal: Dict[str, Any]) -> str:
    """
    Stable-enough signature used to distinguish a new post-click popup from
    anything that was already on screen before the claim click.
    """
    text = _up(modal.get("text", ""))
    buttons = _up(" ".join(modal.get("buttons", []) or []))
    return _short(f"{text} || {buttons}", 700)


def _success_modal_signatures(sb: SB) -> Tuple[str, ...]:
    signatures = []
    for modal in _visible_modal_candidates(sb):
        signature = _modal_signature(modal)
        if signature:
            signatures.append(signature)
    return tuple(signatures)


def _claim_success_evidence(
    sb: SB,
    previous_signatures: Tuple[str, ...] = (),
    pre_click_visible_text: str = "",
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Detects a real successful-claim confirmation.

    Strong accepted combinations:
    1) A NEW visible modal containing CONGRATULATIONS + START PLAYING.
    2) A NEW visible modal containing a generic success phrase + a success action.
    3) A NEW visible modal containing CONGRATULATIONS + both reward amounts
       (10,000 and 1.00), even if the button text is represented graphically.
    4) The same combinations in visible page text when the site does not expose
       a recognizable dialog wrapper.

    A lone "Congratulations" or lone "Start Playing" is never enough.
    Checkout/payment markers always invalidate the candidate.
    """
    previous = set(previous_signatures or ())
    best: Optional[Dict[str, Any]] = None

    for modal in _visible_modal_candidates(sb):
        modal_text = _up(modal.get("text", ""))
        button_text = _up(" ".join(modal.get("buttons", []) or []))
        combined = _up(f"{modal_text} {button_text}")
        signature = _modal_signature(modal)
        is_new = signature not in previous

        title_hit = _first_marker(combined, CLAIM_SUCCESS_TITLE_MARKERS)
        action_hit = _first_marker(combined, CLAIM_SUCCESS_ACTION_MARKERS)
        generic_hit = _first_marker(combined, CLAIM_SUCCESS_GENERIC_MARKERS)

        has_10000 = "10,000" in combined or re.search(r"(?<!\d)10000(?!\d)", combined) is not None
        has_100 = re.search(r"(?<!\d)1(?:[.,]00)(?!\d)", combined) is not None
        has_reward_word = any(
            marker in combined
            for marker in ("GOLD COINS", "SWEEPS COINS", " GC", " SC", "AND")
        )

        score = 0
        if title_hit:
            score += 160
        if action_hit:
            score += 140
        if generic_hit:
            score += 180
        if has_10000:
            score += 60
        if has_100:
            score += 60
        if has_reward_word:
            score += 25
        if is_new:
            score += 80
        if _contains_any(combined, CHECKOUT_MARKERS):
            score -= 500
        if _contains_any(combined, BAD_CONTEXT_MARKERS):
            score -= 300

        strong_combo = (
            (bool(title_hit) and bool(action_hit))
            or (bool(generic_hit) and bool(action_hit))
            or (bool(title_hit) and has_10000 and has_100)
        )

        # When previous_signatures were supplied, require this popup to be new.
        matched = strong_combo and (not previous or is_new) and score >= 300

        if verbose:
            print(
                "[Zula] Success modal candidate: "
                f"score={score} new={is_new} matched={matched} "
                f"title={title_hit or '-'} action={action_hit or '-'} "
                f"generic={generic_hit or '-'} "
                f"text='{_short(combined, 180)}'"
            )

        if matched:
            candidate = {
                "matched": True,
                "source": "new_success_modal",
                "score": score,
                "evidence": _short(combined, 220),
                "signature": signature,
            }

            if best is None or score > int(best.get("score", 0)):
                best = candidate

    if best:
        return best

    # Fallback: sometimes the wrapper has no modal/dialog-ish class, but the
    # visible document still contains the exact success popup text.
    visible_text = _up(_visible_page_text(sb))
    before_text = _up(pre_click_visible_text)

    title_hit = _first_marker(visible_text, CLAIM_SUCCESS_TITLE_MARKERS)
    action_hit = _first_marker(visible_text, CLAIM_SUCCESS_ACTION_MARKERS)
    generic_hit = _first_marker(visible_text, CLAIM_SUCCESS_GENERIC_MARKERS)
    has_10000 = "10,000" in visible_text or re.search(r"(?<!\d)10000(?!\d)", visible_text) is not None
    has_100 = re.search(r"(?<!\d)1(?:[.,]00)(?!\d)", visible_text) is not None

    before_had_combo = (
        (
            _first_marker(before_text, CLAIM_SUCCESS_TITLE_MARKERS)
            and _first_marker(before_text, CLAIM_SUCCESS_ACTION_MARKERS)
        )
        or (
            _first_marker(before_text, CLAIM_SUCCESS_GENERIC_MARKERS)
            and _first_marker(before_text, CLAIM_SUCCESS_ACTION_MARKERS)
        )
        or (
            _first_marker(before_text, CLAIM_SUCCESS_TITLE_MARKERS)
            and ("10,000" in before_text or "10000" in before_text)
            and re.search(r"(?<!\d)1(?:[.,]00)(?!\d)", before_text) is not None
        )
    )

    strong_page_combo = (
        (bool(title_hit) and bool(action_hit))
        or (bool(generic_hit) and bool(action_hit))
        or (bool(title_hit) and has_10000 and has_100)
    )

    if (
        strong_page_combo
        and not before_had_combo
        and not _contains_any(visible_text, CHECKOUT_MARKERS)
        and not _contains_any(visible_text, BAD_CONTEXT_MARKERS)
    ):
        evidence_parts = [
            title_hit,
            generic_hit,
            action_hit,
            "10,000" if has_10000 else "",
            "1.00" if has_100 else "",
        ]

        return {
            "matched": True,
            "source": "visible_text_success_combo",
            "score": 320,
            "evidence": " + ".join(part for part in evidence_parts if part),
            "signature": "",
        }

    return None


def _daily_claim_snapshot(sb: SB) -> Dict[str, Any]:
    """
    Captures the daily reward card before/after a click for additional state
    diagnostics without changing the candidate-based click strategy.
    """
    pkg = _daily_package(sb, verbose=False)

    if not pkg:
        return {
            "found": False,
            "text": "",
            "claimedMarker": "",
            "enabledClaimButtons": (),
        }

    enabled_claim_buttons = []

    for btn in pkg.get("buttons", []):
        if btn.get("disabled"):
            continue

        btn_text = _up(
            " ".join(
                [
                    btn.get("text", ""),
                    btn.get("aria", ""),
                    btn.get("title", ""),
                ]
            )
        )

        if "COLLECT" in btn_text or "CLAIM" in btn_text:
            enabled_claim_buttons.append(btn_text)

    pkg_text = _norm(pkg.get("text", ""))

    return {
        "found": True,
        "text": pkg_text,
        "claimedMarker": _first_marker(pkg_text, CLAIMED_MARKERS),
        "enabledClaimButtons": tuple(enabled_claim_buttons),
    }


def _daily_transition_evidence(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Secondary card-level evidence.

    This is intentionally conservative: button disappearance by itself does
    not count. The after-state must also contain a known claimed/tomorrow marker.
    """
    claimed_marker = after.get("claimedMarker", "")

    if claimed_marker:
        return {
            "matched": True,
            "source": "daily_card_transition",
            "score": 300,
            "evidence": claimed_marker,
        }

    return None


def _reward_packages(sb: SB) -> List[Dict[str, Any]]:
    """
    Finds Zula coin-store reward packages and tags buttons with temporary candidate IDs.
    This is the main candidate system.
    """
    packages = _safe_js(
        sb,
        """
        const visible = (el) => {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== "none"
                && s.visibility !== "hidden"
                && s.opacity !== "0"
                && r.width > 0
                && r.height > 0;
        };

        const packageSelectors = [
            ".coin-store-reward-package",
            "[data-sentry-component='CoinStoreRewardPackage']",
            "div[class*='coin-store-reward-package']",
            "div[class*='reward-package']"
        ];

        const seen = new Set();
        const found = [];

        for (const selector of packageSelectors) {
            for (const el of Array.from(document.querySelectorAll(selector))) {
                const pkg = el.closest(".coin-store-reward-package")
                    || el.closest("[data-sentry-component='CoinStoreRewardPackage']")
                    || el;

                if (!pkg || seen.has(pkg) || !visible(pkg)) continue;

                const text = (pkg.innerText || pkg.textContent || "").trim();
                if (!text) continue;

                seen.add(pkg);
                found.push(pkg);
            }
        }

        return found.map((pkg, pkgIndex) => {
            pkg.setAttribute("data-zula-package-id", `pkg-${pkgIndex}`);

            const buttons = Array.from(
                pkg.querySelectorAll("button, [role='button'], a, input[type='button'], input[type='submit']")
            )
                .filter(visible)
                .map((btn, btnIndex) => {
                    const candidateId = `pkg-${pkgIndex}-btn-${btnIndex}`;
                    btn.setAttribute("data-zula-candidate-id", candidateId);

                    return {
                        candidateId,
                        text: (btn.innerText || btn.textContent || btn.value || "").trim(),
                        aria: (btn.getAttribute("aria-label") || "").trim(),
                        title: (btn.getAttribute("title") || "").trim(),
                        disabled: !!btn.disabled || btn.getAttribute("aria-disabled") === "true",
                        classes: btn.className ? String(btn.className) : ""
                    };
                });

            return {
                index: pkgIndex,
                text: (pkg.innerText || pkg.textContent || "").trim(),
                classes: pkg.className ? String(pkg.className) : "",
                buttons
            };
        });
        """,
        default=[],
    )

    return packages if isinstance(packages, list) else []


def _global_button_candidates(sb: SB) -> List[Dict[str, Any]]:
    """
    Fallback broad scan of clickable elements.
    Used only if package scan fails.
    """
    candidates = _safe_js(
        sb,
        """
        const visible = (el) => {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== "none"
                && s.visibility !== "hidden"
                && s.opacity !== "0"
                && r.width > 0
                && r.height > 0;
        };

        return Array.from(
            document.querySelectorAll("button, [role='button'], a, input[type='button'], input[type='submit']")
        )
            .filter(visible)
            .map((el, index) => {
                const candidateId = `global-${index}`;
                el.setAttribute("data-zula-candidate-id", candidateId);

                const parent = el.closest(".coin-store-reward-package")
                    || el.closest("[data-sentry-component='CoinStoreRewardPackage']")
                    || el.closest("section")
                    || el.closest("article")
                    || el.closest("nav")
                    || el.closest("header")
                    || el.parentElement;

                return {
                    candidateId,
                    text: (el.innerText || el.textContent || el.value || "").trim(),
                    aria: (el.getAttribute("aria-label") || "").trim(),
                    title: (el.getAttribute("title") || "").trim(),
                    disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
                    contextText: parent ? ((parent.innerText || parent.textContent || "").trim()) : ""
                };
            });
        """,
        default=[],
    )

    return candidates if isinstance(candidates, list) else []


def _score_daily_package(pkg: Dict[str, Any]) -> int:
    text = _up(pkg.get("text", ""))
    index = int(pkg.get("index", 999))
    score = 0

    if "DAILY BONUS" in text:
        score += 120

    if "TODAY'S BONUS" in text or "TODAYS BONUS" in text:
        score += 120

    if "SEE YOU TOMORROW" in text:
        score += 80

    if "FREE SC" in text or "+ FREE" in text:
        score += 45

    if " GC" in text or "GC " in text:
        score += 15

    # Daily bonus card is normally the first reward card.
    if index == 0:
        score += 35

    if _contains_any(text, BAD_CONTEXT_MARKERS):
        score -= 250

    return score


def _daily_package(sb: SB, verbose: bool = False) -> Optional[Dict[str, Any]]:
    packages = _reward_packages(sb)

    if not packages:
        return None

    for pkg in packages:
        pkg["_score"] = _score_daily_package(pkg)

    packages.sort(key=lambda item: item.get("_score", 0), reverse=True)

    if verbose:
        print("[Zula] Reward package candidates:")
        for pkg in packages[:8]:
            print(
                f"  - score={pkg.get('_score')} "
                f"idx={pkg.get('index')} "
                f"text='{_short(pkg.get('text'), 140)}'"
            )

    best = packages[0]
    return best if best.get("_score", 0) > 0 else None


def _zula_state(
    sb: SB,
    verbose: bool = False,
    allow_claim_success: bool = False,
    previous_success_signatures: Tuple[str, ...] = (),
    pre_click_visible_text: str = "",
) -> Dict[str, str]:
    """
    Returns:
    - checkout
    - claim_success
    - daily_claimed
    - rewards_modal
    - login
    - unknown

    claim_success is only evaluated in the post-click phase.
    """
    page_text = _page_text(sb)

    # Checkout wins first because payment/checkout must never be counted as a claim.
    checkout_hit = _first_marker(page_text, CHECKOUT_MARKERS)
    if checkout_hit:
        return {
            "status": "checkout",
            "reason": "Checkout/payment page detected",
            "evidence": checkout_hit,
        }

    if allow_claim_success:
        success = _claim_success_evidence(
            sb,
            previous_signatures=previous_success_signatures,
            pre_click_visible_text=pre_click_visible_text,
            verbose=verbose,
        )

        if success:
            return {
                "status": "claim_success",
                "reason": "Successful daily-claim confirmation popup/text detected",
                "evidence": str(success.get("evidence", "")),
            }

    pkg = _daily_package(sb, verbose=verbose)

    if pkg:
        pkg_text = pkg.get("text", "")
        claimed_hit = _first_marker(pkg_text, CLAIMED_MARKERS)

        if claimed_hit:
            return {
                "status": "daily_claimed",
                "reason": "Daily package says already claimed",
                "evidence": claimed_hit,
            }

    claimed_hit = _first_marker(page_text, CLAIMED_MARKERS)
    if claimed_hit:
        return {
            "status": "daily_claimed",
            "reason": "Page says daily bonus is claimed",
            "evidence": claimed_hit,
        }

    rewards_hit = _first_marker(page_text, REWARDS_MARKERS)
    if rewards_hit:
        return {
            "status": "rewards_modal",
            "reason": "Rewards modal is open",
            "evidence": rewards_hit,
        }

    upper = _up(page_text)

    if "LOGIN" in upper and ("EMAIL" in upper or "PASSWORD" in upper):
        return {
            "status": "login",
            "reason": "Login form detected",
            "evidence": "LOGIN",
        }

    return {
        "status": "unknown",
        "reason": "Unknown page state",
        "evidence": _short(page_text, 100),
    }


def _wait_for_state(
    sb: SB,
    wanted: Tuple[str, ...],
    timeout: float = 8,
    step: float = 1,
    allow_claim_success: bool = False,
    previous_success_signatures: Tuple[str, ...] = (),
    pre_click_visible_text: str = "",
) -> Dict[str, str]:
    """
    Polls state until one of the wanted states appears.

    The first scan happens immediately so short-lived success popups are not
    missed. Post-click callers can enable claim_success detection and provide
    the pre-click modal/text snapshots.
    """
    deadline = time.monotonic() + max(0.1, timeout)
    last: Dict[str, str] = {
        "status": "unknown",
        "reason": "State polling has not started",
        "evidence": "",
    }

    while True:
        last = _zula_state(
            sb,
            verbose=True,
            allow_claim_success=allow_claim_success,
            previous_success_signatures=previous_success_signatures,
            pre_click_visible_text=pre_click_visible_text,
        )

        print(
            f"[Zula] State={last['status']} "
            f"reason={last['reason']} "
            f"evidence={last['evidence']}"
        )

        if last["status"] in wanted:
            return last

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return last

        sb.wait(min(step, remaining))



def _find_daily_claim_candidate(sb: SB) -> Optional[Dict[str, Any]]:
    """
    Finds the safest daily bonus claim button.

    Main path:
    - Locate reward packages.
    - Pick the daily package.
    - Refuse if that package says TODAY'S BONUS IS CLAIMED.
    - Click only Collect/Claim inside that package.

    Fallback:
    - Broad button scan, but only if context strongly mentions daily/free reward.
    """
    pkg = _daily_package(sb, verbose=True)

    if pkg:
        pkg_text = pkg.get("text", "")
        pkg_upper = _up(pkg_text)

        if _contains_any(pkg_upper, CLAIMED_MARKERS):
            print("[Zula] Daily package is already claimed; refusing to click.")
            return None

        if _contains_any(pkg_upper, BAD_CONTEXT_MARKERS):
            print("[Zula] Daily package candidate looks like checkout/social/payment; refusing to click.")
            return None

        for btn in pkg.get("buttons", []):
            if btn.get("disabled"):
                continue

            btn_text = _up(
                " ".join(
                    [
                        btn.get("text", ""),
                        btn.get("aria", ""),
                        btn.get("title", ""),
                    ]
                )
            )

            if "COLLECT" in btn_text or "CLAIM" in btn_text:
                return {
                    "candidateId": btn.get("candidateId", ""),
                    "source": "daily_package",
                    "score": pkg.get("_score", 0),
                    "buttonText": _short(btn_text, 80),
                    "contextText": _short(pkg_text, 160),
                }

        print("[Zula] Daily package found, but no enabled Collect/Claim button was inside it.")

    scored = []

    for cand in _global_button_candidates(sb):
        if cand.get("disabled"):
            continue

        text = _up(
            " ".join(
                [
                    cand.get("text", ""),
                    cand.get("aria", ""),
                    cand.get("title", ""),
                ]
            )
        )
        context = _up(cand.get("contextText", ""))
        combined = f"{text} {context}"

        score = 0

        if "COLLECT" in text or "CLAIM" in text:
            score += 60

        if "DAILY BONUS" in combined:
            score += 110

        if "TODAY'S BONUS" in combined or "TODAYS BONUS" in combined:
            score += 110

        if "FREE SC" in combined or "+ FREE" in combined:
            score += 35

        if "COIN STORE" in combined or "CLAIM FREE REWARDS" in combined:
            score += 15

        if _contains_any(combined, CLAIMED_MARKERS):
            score -= 300

        if _contains_any(combined, BAD_CONTEXT_MARKERS):
            score -= 250

        cand["_score"] = score
        scored.append(cand)

    scored.sort(key=lambda item: item.get("_score", 0), reverse=True)

    print("[Zula] Global claim fallback candidates:")
    for cand in scored[:8]:
        print(
            f"  - score={cand.get('_score')} "
            f"text='{_short(cand.get('text'), 60)}' "
            f"context='{_short(cand.get('contextText'), 120)}'"
        )

    if scored and scored[0].get("_score", 0) >= 130:
        best = scored[0]

        return {
            "candidateId": best.get("candidateId", ""),
            "source": "global_fallback",
            "score": best.get("_score", 0),
            "buttonText": _short(best.get("text", "") or best.get("aria", ""), 80),
            "contextText": _short(best.get("contextText", ""), 160),
        }

    return None


# ───────────────────────────────────────────────────────────
# Main UC-based flow
# ───────────────────────────────────────────────────────────

async def zula_uc(ctx, channel: discord.abc.Messageable):
    """
    Zula via SeleniumBase UC.

    Login flow is intentionally kept from the original file:
    - open login
    - type email/password
    - wait 10
    - uc_gui_click_captcha
    - press enter on password
    - wait 8
    - refresh
    - close lobby popups

    Claim flow is upgraded:
    - open rewards modal
    - scan page/package text for TODAY'S BONUS IS CLAIMED
    - scan for CHECKOUT/payment false-positive page
    - find the daily bonus package
    - click only that package's Collect/Claim candidate
    - verify either claimed/tomorrow text OR the new
      CONGRATULATIONS + START PLAYING success popup
    - compare post-click popup/text against pre-click state before sending
      "Zula Daily Bonus Claimed!"
    """
    await channel.send("Launching **Zula** (UC)…")

    if ":" not in ZULA_CRED:
        await channel.send("❌ Missing `ZULA` as 'email:password' in your .env.")
        return

    username, password = ZULA_CRED.split(":", 1)

    try:
        with SB(uc=True, headed=True) as sb:
            # 1) Login — kept from your original flow
            sb.uc_open_with_reconnect("https://www.zulacasino.com/login", 4)
            sb.wait_for_ready_state_complete()
            print("[Zula] Login page loaded.")

            try:
                sb.type("input[id='emailAddress']", username)
                sb.type("input[id='password']", password)

                try:
                    sb.wait(10)
                    sb.uc_gui_click_captcha()
                except Exception:
                    pass

            except Exception as e:
                print(f"[Zula][ERROR] Login fields not found: {e}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] countdown not available (or auth failed).",
                    "zula_unavailable",
                )
                return

            # Submit login — kept from your original flow
            submitted = False

            try:
                sb.press_keys("input[id='password']", "\n")
                submitted = True
            except Exception:
                pass

            if not submitted:
                submitted = _try_click_any(
                    sb,
                    [
                        "//button[@type='submit']",
                        "//button[contains(.,'Log in')]",
                        "//button[contains(.,'Login')]",
                        "//button[contains(.,'Sign in')]",
                    ],
                    timeout_each=10,
                )

            if not submitted:
                print("[Zula][ERROR] Could not submit login.")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] countdown not available (or auth failed).",
                    "zula_unavailable",
                )
                return

            # 2) Post-login settle and refresh into lobby — kept from your original flow
            sb.wait(8)
            sb.refresh_page()
            sb.wait_for_ready_state_complete()
            print("[Zula] Post-login refresh complete (lobby expected).")

            # 3) Close 0/1/2 lobby popups — kept from your original flow
            _close_lobby_popups_flexible(sb)

            # 4) Extra safety cleanup — kept from your original flow
            _extra_popup_cleanup(sb)

            # 5) Open Rewards / Free Coins — same idea as original, only safer fallbacks added
            opened_rewards = _try_click_any(
                sb,
                [
                    "/html/body/div[1]/div[2]/div[1]/div/nav/div[2]/button[1]",
                    "/html/body/div[1]/div[2]/div/nav/div[2]/button[1]",
                    "//button[contains(.,'Free Coins') or contains(.,'Rewards') or contains(.,'Get Coins')]",
                    "//button[.//*[contains(.,'Free Coins') or contains(.,'Rewards') or contains(.,'Get Coins')]]",
                ],
                timeout_each=12,
            )

            if not opened_rewards:
                print("[Zula] Rewards/Free Coins button not found.")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Rewards button not found. Not marking as claimed.",
                    "zula_rewards_not_found",
                )
                return

            sb.wait(10)
            print("[Zula] Rewards modal should be open.")

            # 6) Before clicking anything, understand the page state
            pre_state = _wait_for_state(
                sb,
                wanted=("daily_claimed", "checkout", "rewards_modal"),
                timeout=6,
                step=1,
            )

            if pre_state["status"] == "checkout":
                print(f"[Zula] Checkout detected before claim: {pre_state}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Checkout/payment page detected. Not marking as claimed.",
                    "zula_checkout_pre",
                )
                return

            if pre_state["status"] == "daily_claimed":
                print(f"[Zula] Already claimed before click: {pre_state}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Daily Bonus unavailable.",
                    "zula_already_claimed",
                )
                return

            # 7) Find the safe daily-bonus Collect/Claim candidate
            candidate = _find_daily_claim_candidate(sb)

            if not candidate:
                state = _zula_state(sb, verbose=True)

                if state["status"] == "daily_claimed":
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Bonus unavailable — today's bonus is already claimed.",
                        "zula_already_claimed",
                    )
                    return

                if state["status"] == "checkout":
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Checkout/payment page detected. Not marking as claimed.",
                        "zula_checkout",
                    )
                    return

                print("[Zula] No safe daily bonus claim candidate found.")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] No safe daily bonus claim button found. Not marking as claimed.",
                    "zula_no_safe_candidate",
                )
                return

            print(f"[Zula] Selected claim candidate: {candidate}")

            # Capture pre-click state so an old/open popup cannot be mistaken
            # for the result of this specific claim click.
            pre_success_signatures = _success_modal_signatures(sb)
            pre_click_visible_text = _visible_page_text(sb)
            pre_daily_snapshot = _daily_claim_snapshot(sb)

            print(
                "[Zula] Pre-click verification snapshot: "
                f"modal_signatures={len(pre_success_signatures)} "
                f"daily_found={pre_daily_snapshot.get('found')} "
                f"claim_buttons={len(pre_daily_snapshot.get('enabledClaimButtons', ()))}"
            )

            # 8) Click only the selected daily reward candidate
            clicked = _click_candidate(sb, candidate.get("candidateId", ""))

            if not clicked:
                print("[Zula] Candidate found but click failed.")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Found daily bonus candidate but could not click it. Not marking as claimed.",
                    "zula_candidate_click_failed",
                )
                return

            # Do not sleep for several seconds before checking. Scan quickly so
            # even a short-lived confirmation popup can be captured.
            sb.wait(0.35)

            # 9) Verify after click. Accepted success states are:
            #    - exact/contains-text Congratulations + Start Playing popup
            #    - generic success popup combinations
            #    - daily card/page changes to claimed/tomorrow text
            # Checkout still wins and is never counted.
            final_state = _wait_for_state(
                sb,
                wanted=("claim_success", "daily_claimed", "checkout"),
                timeout=12,
                step=0.5,
                allow_claim_success=True,
                previous_success_signatures=pre_success_signatures,
                pre_click_visible_text=pre_click_visible_text,
            )

            if final_state["status"] == "checkout":
                print(f"[Zula] False-positive prevented. Final state: {final_state}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Click led to checkout/payment, so this was not counted as a daily bonus claim.",
                    "zula_checkout_false_positive",
                )
                return

            if final_state["status"] in ("claim_success", "daily_claimed"):
                print(f"[Zula] Claimed successfully and verified: {final_state}")
                await _send_post_claim(
                    sb,
                    channel,
                    "zula_claimed.png",
                    "Zula Daily Bonus Claimed!",
                )
                return

            # Final direct contains-text/modal check in case state polling ended
            # between a DOM update and the reward-card refresh.
            final_success = _claim_success_evidence(
                sb,
                previous_signatures=pre_success_signatures,
                pre_click_visible_text=pre_click_visible_text,
                verbose=True,
            )

            if final_success:
                print(f"[Zula] Claimed successfully via final success check: {final_success}")
                await _send_post_claim(
                    sb,
                    channel,
                    "zula_claimed.png",
                    "Zula Daily Bonus Claimed!",
                )
                return

            post_daily_snapshot = _daily_claim_snapshot(sb)
            transition = _daily_transition_evidence(
                pre_daily_snapshot,
                post_daily_snapshot,
            )

            if transition:
                print(f"[Zula] Claimed successfully via daily-card transition: {transition}")
                await _send_post_claim(
                    sb,
                    channel,
                    "zula_claimed.png",
                    "Zula Daily Bonus Claimed!",
                )
                return

            print(
                "[Zula] Claim click was not verified. "
                f"Final state={final_state}; "
                f"pre_daily={pre_daily_snapshot}; "
                f"post_daily={post_daily_snapshot}"
            )
            await _send_status_shot(
                sb,
                channel,
                "[Zula] Claim click happened, but no success popup or claimed-state text was found. Not marking as claimed.",
                "zula_unverified",
            )
            return

    except Exception as e:
        print(f"[Zula][ERROR] Exception during automation: {e}")

        try:
            with SB(uc=True, headed=True) as sb_fallback:
                await _send_status_shot(
                    sb_fallback,
                    channel,
                    "[Zula] Error during automation. Not marking as claimed.",
                    "zula_error",
                )
        except Exception:
            await channel.send("[Zula] Error during automation. Not marking as claimed.")