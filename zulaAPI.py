# Drake Hooks + WaterTrooper
# Casino Claim 3
# Zula API (SeleniumBase UC; original login flow + candidate/state-based claim detection)
# Exposes: async def zula_uc(ctx, channel)

import os
import re
import tempfile
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


def _zula_state(sb: SB, verbose: bool = False) -> Dict[str, str]:
    """
    Returns:
    - checkout
    - daily_claimed
    - rewards_modal
    - login
    - unknown
    """
    page_text = _page_text(sb)

    # Checkout wins first because this is the exact false-positive page.
    checkout_hit = _first_marker(page_text, CHECKOUT_MARKERS)
    if checkout_hit:
        return {
            "status": "checkout",
            "reason": "Checkout/payment page detected",
            "evidence": checkout_hit,
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


def _wait_for_state(sb: SB, wanted: Tuple[str, ...], timeout: float = 8, step: float = 1) -> Dict[str, str]:
    loops = max(1, int(timeout / step))
    last = _zula_state(sb, verbose=True)

    for _ in range(loops):
        last = _zula_state(sb, verbose=True)

        print(
            f"[Zula] State={last['status']} "
            f"reason={last['reason']} "
            f"evidence={last['evidence']}"
        )

        if last["status"] in wanted:
            return last

        sb.wait(step)

    return last


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
    - verify claimed text before sending "Zula Daily Bonus Claimed!"
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

            sb.wait(3)

            # 9) Verify after click. This prevents the screenshot false-positive.
            final_state = _wait_for_state(
                sb,
                wanted=("daily_claimed", "checkout"),
                timeout=10,
                step=1,
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

            if final_state["status"] == "daily_claimed":
                print(f"[Zula] Claimed successfully and verified: {final_state}")
                await _send_post_claim(
                    sb,
                    channel,
                    "zula_claimed.png",
                    "Zula Daily Bonus Claimed!",
                )
                return

            print(f"[Zula] Claim click was not verified. Final state: {final_state}")
            await _send_status_shot(
                sb,
                channel,
                "[Zula] Claim click happened, but the page did not confirm a daily claim. Not marking as claimed.",
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