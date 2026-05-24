# Drake Hooks + WaterTrooper
# Casino Claim 3
# Zula API (SeleniumBase UC; page-state + candidate based daily bonus claim)
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

ZULA_LOGIN_URL = "https://www.zulacasino.com/login"
ZULA_LOBBY_URL = "https://www.zulacasino.com/lobby"

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
)

REWARDS_MARKERS = (
    "COIN STORE",
    "CLAIM FREE REWARDS",
    "FREE REWARDS",
    "SPECIAL OFFERS",
)

BAD_CONTEXT = (
    "FACEBOOK CONNECT",
    "GOOGLE CONNECT",
    "CREDIT/DEBIT",
    "PAYMENT METHOD",
    "CHECKOUT",
    "ORDER SUMMARY",
    "SKRILL",
    "PAY USING",
)


# ───────────────────────────────────────────────────────────
# Text / screenshot helpers
# ───────────────────────────────────────────────────────────
def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\xa0", " ").replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", value).strip()


def _up(value: Any) -> str:
    return _norm(value).upper()


def _has(text: Any, markers: Tuple[str, ...]) -> bool:
    upper = _up(text)
    return any(marker in upper for marker in markers)


def _marker(text: Any, markers: Tuple[str, ...]) -> str:
    upper = _up(text)
    for marker in markers:
        if marker in upper:
            return marker
    return ""


def _short(text: Any, limit: int = 150) -> str:
    text = _norm(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


async def _send_post_claim(sb: SB, channel: discord.abc.Messageable, path: str, caption: str):
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
    fd, tmp_path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".png", dir="/tmp")
    os.close(fd)

    try:
        sb.save_screenshot(tmp_path)
        await channel.send(caption, file=discord.File(tmp_path))
    except Exception as e:
        print(f"[Zula][WARN] screenshot failed: {e}")
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


def _js(sb: SB, script: str, *args, default=None):
    try:
        return sb.execute_script(script, *args)
    except Exception as e:
        print(f"[Zula][JS] failed: {e}")
        return default


# ───────────────────────────────────────────────────────────
# Click helpers
# ───────────────────────────────────────────────────────────
def _force_click_xpath(sb: SB, xpath: str, timeout: float = 10) -> bool:
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
            pass

    return False


def _try_xpaths(sb: SB, xpaths: List[str], timeout_each: float = 8) -> bool:
    for xp in xpaths:
        if xp and _force_click_xpath(sb, xp, timeout_each):
            return True
    return False


def _click_candidate(sb: SB, candidate_id: str) -> bool:
    if not candidate_id:
        return False

    selector = f"[data-zula-candidate-id='{candidate_id}']"

    try:
        sb.scroll_to(selector)
    except Exception:
        pass

    for mode in ("normal", "js_click", "dispatch"):
        try:
            if mode == "normal":
                sb.click(selector, timeout=2)
                return True

            if mode == "js_click":
                sb.js_click(selector)
                return True

            ok = _js(
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
            pass

    return False


# ───────────────────────────────────────────────────────────
# Popup cleanup
# ───────────────────────────────────────────────────────────
def _close_popups(sb: SB):
    popup_xpaths = [
        "/html/body/div[4]/div/div[1]/div/div/button",
        "/html/body/div[5]/div/div[1]/div/div/button",
        "/html/body/div[6]/div/div[1]/div/div/button",
        "//button[contains(@class,'dialog-close-button')]",
        "//button[contains(@aria-label,'Close') or contains(@aria-label,'close')]",
        "//button[contains(translate(., 'CLOSE', 'close'), 'close')]",
        "//button[contains(., 'Accept All')]",
        "//button[contains(., 'Accept')]",
        "//button[contains(., 'Got it')]",
    ]

    closed = 0

    for _ in range(3):
        if _try_xpaths(sb, popup_xpaths, timeout_each=2.5):
            closed += 1
            sb.wait(0.5)

    try:
        sb.press_keys("body", "ESCAPE")
    except Exception:
        pass

    print(f"[Zula] Popup/banner cleanup clicks: {closed}")


# ───────────────────────────────────────────────────────────
# Page scanning / candidate system
# ───────────────────────────────────────────────────────────
def _page_text(sb: SB) -> str:
    """
    Broad scan of body text and visible element text.
    This catches claimed/checkout text even when the XPath/classes change.
    """
    data = _js(
        sb,
        """
        const visible = (el) => {
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== "none"
                && s.visibility !== "hidden"
                && s.opacity !== "0"
                && r.width > 0
                && r.height > 0;
        };

        const elementText = Array.from(document.querySelectorAll("body *"))
            .filter(visible)
            .map((el) => [
                el.innerText || el.textContent || el.value || "",
                el.getAttribute("aria-label") || "",
                el.getAttribute("title") || "",
                el.getAttribute("role") || ""
            ].join(" "))
            .join(" ");

        return {
            url: window.location.href,
            title: document.title || "",
            body: document.body ? (document.body.innerText || document.body.textContent || "") : "",
            elements: elementText
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
                data.get("elements", ""),
            ]
        )
    )


def _reward_packages(sb: SB) -> List[Dict[str, Any]]:
    """
    Finds the cards/packages in the coin store and tags their buttons with data-zula-candidate-id.
    """
    packages = _js(
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
            ".coin-store-reward-package",
            "[data-sentry-component='CoinStoreRewardPackage']",
            "div[class*='coin-store-reward-package']",
            "div[class*='reward-package']"
        ];

        const seen = new Set();
        const found = [];

        for (const selector of selectors) {
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


def _global_candidates(sb: SB) -> List[Dict[str, Any]]:
    candidates = _js(
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
        score += 70
    if "FREE SC" in text or "+ FREE" in text:
        score += 40
    if " GC" in text or "GC " in text:
        score += 15

    # Zula's daily bonus card is normally the first reward package.
    if index == 0:
        score += 35

    if _has(text, BAD_CONTEXT):
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
        for pkg in packages[:6]:
            print(
                f"  - score={pkg.get('_score')} "
                f"idx={pkg.get('index')} "
                f"text='{_short(pkg.get('text'), 120)}'"
            )

    best = packages[0]
    return best if best.get("_score", 0) > 0 else None


def _zula_state(sb: SB, verbose: bool = False) -> Dict[str, str]:
    """
    Returns one of:
    - checkout
    - daily_claimed
    - rewards_modal
    - login
    - unknown
    """
    text = _page_text(sb)

    # Checkout wins because checkout can appear over the coin-store modal.
    hit = _marker(text, CHECKOUT_MARKERS)
    if hit:
        return {
            "status": "checkout",
            "reason": "Checkout/payment page detected",
            "evidence": hit,
        }

    pkg = _daily_package(sb, verbose=verbose)
    if pkg:
        hit = _marker(pkg.get("text", ""), CLAIMED_MARKERS)
        if hit:
            return {
                "status": "daily_claimed",
                "reason": "Daily package says already claimed",
                "evidence": hit,
            }

    hit = _marker(text, CLAIMED_MARKERS)
    if hit:
        return {
            "status": "daily_claimed",
            "reason": "Page says daily/today bonus is claimed",
            "evidence": hit,
        }

    hit = _marker(text, REWARDS_MARKERS)
    if hit:
        return {
            "status": "rewards_modal",
            "reason": "Rewards modal is open",
            "evidence": hit,
        }

    upper = _up(text)
    if "LOGIN" in upper and ("EMAIL" in upper or "PASSWORD" in upper):
        return {
            "status": "login",
            "reason": "Login form detected",
            "evidence": "LOGIN",
        }

    return {
        "status": "unknown",
        "reason": "Unknown page state",
        "evidence": _short(text, 100),
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
    Primary path:
      1. Find reward packages/cards.
      2. Pick the daily package.
      3. Click Collect/Claim inside ONLY that package.

    Fallback path:
      Use broad button scan only if the button context strongly says daily bonus/free SC.
    """
    pkg = _daily_package(sb, verbose=True)

    if pkg:
        pkg_text = _up(pkg.get("text", ""))

        if _has(pkg_text, CLAIMED_MARKERS):
            print("[Zula] Daily package is already claimed; refusing to click.")
            return None

        if _has(pkg_text, BAD_CONTEXT):
            print("[Zula] Best package looks like payment/social connect; refusing to click.")
            return None

        for btn in pkg.get("buttons", []):
            btn_text = _up(
                " ".join(
                    [
                        btn.get("text", ""),
                        btn.get("aria", ""),
                        btn.get("title", ""),
                    ]
                )
            )

            if btn.get("disabled"):
                continue

            if "COLLECT" in btn_text or "CLAIM" in btn_text:
                return {
                    "candidateId": btn.get("candidateId", ""),
                    "source": "daily_package",
                    "score": pkg.get("_score", 0),
                    "buttonText": _short(btn_text, 80),
                    "contextText": _short(pkg.get("text", ""), 160),
                }

        print("[Zula] Daily package found, but no enabled Collect/Claim button was inside it.")

    scored = []

    for cand in _global_candidates(sb):
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

        if _has(combined, CLAIMED_MARKERS):
            score -= 300
        if _has(combined, BAD_CONTEXT):
            score -= 250

        cand["_score"] = score
        scored.append(cand)

    scored.sort(key=lambda item: item.get("_score", 0), reverse=True)

    print("[Zula] Global claim fallback candidates:")
    for cand in scored[:8]:
        print(
            f"  - score={cand.get('_score')} "
            f"text='{_short(cand.get('text'), 50)}' "
            f"context='{_short(cand.get('contextText'), 100)}'"
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


def _open_rewards_modal(sb: SB) -> bool:
    _close_popups(sb)

    # Keep known working header XPaths for opening rewards/store.
    # Do NOT use these for claiming the reward.
    if _try_xpaths(
        sb,
        [
            "/html/body/div[1]/div[2]/div[1]/div/nav/div[2]/button[1]",
            "/html/body/div[1]/div[2]/div/nav/div[2]/button[1]",
            "//button[contains(.,'Free Coins') or contains(.,'Rewards') or contains(.,'Get Coins') or contains(.,'Coins')]",
            "//button[.//*[contains(.,'Free Coins') or contains(.,'Rewards') or contains(.,'Get Coins') or contains(.,'Coins')]]",
        ],
        timeout_each=8,
    ):
        return True

    scored = []

    for cand in _global_candidates(sb):
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

        if "FREE COINS" in combined:
            score += 100
        if "REWARDS" in combined:
            score += 90
        if "GET COINS" in combined:
            score += 75
        if "COINS" in combined or "COIN" in combined:
            score += 35
        if "DAILY BONUS" in combined:
            score += 60
        if "MENU" in combined:
            score -= 30
        if _has(combined, CHECKOUT_MARKERS):
            score -= 200

        cand["_score"] = score
        scored.append(cand)

    scored.sort(key=lambda item: item.get("_score", 0), reverse=True)

    print("[Zula] Rewards open candidates:")
    for cand in scored[:8]:
        print(
            f"  - score={cand.get('_score')} "
            f"text='{_short(cand.get('text'), 50)}' "
            f"context='{_short(cand.get('contextText'), 100)}'"
        )

    return bool(
        scored
        and scored[0].get("_score", 0) >= 70
        and _click_candidate(sb, scored[0].get("candidateId", ""))
    )


# ───────────────────────────────────────────────────────────
# Login
# ───────────────────────────────────────────────────────────
def _login_zula(sb: SB, username: str, password: str) -> bool:
    sb.uc_open_with_reconnect(ZULA_LOGIN_URL, 4)
    sb.wait_for_ready_state_complete()
    print("[Zula] Login page loaded.")

    try:
        sb.wait_for_element_visible("input[id='emailAddress']", timeout=18)
        sb.type("input[id='emailAddress']", username, timeout=8)
        sb.type("input[id='password']", password, timeout=8)
    except Exception as e:
        print(f"[Zula][ERROR] Login fields not found/typeable: {e}")
        return False

    try:
        sb.wait(4)
        sb.uc_gui_click_captcha()
    except Exception:
        pass

    submitted = False

    try:
        sb.press_keys("input[id='password']", "\n")
        submitted = True
    except Exception:
        pass

    if not submitted:
        submitted = _try_xpaths(
            sb,
            [
                "//button[@type='submit']",
                "//button[contains(.,'Log in')]",
                "//button[contains(.,'Login')]",
                "//button[contains(.,'Sign in')]",
            ],
            timeout_each=8,
        )

    if not submitted:
        print("[Zula][ERROR] Could not submit login.")
        return False

    sb.wait(8)
    sb.wait_for_ready_state_complete()

    try:
        sb.uc_open_with_reconnect(ZULA_LOBBY_URL, 3)
        sb.wait_for_ready_state_complete()
    except Exception:
        try:
            sb.open(ZULA_LOBBY_URL)
            sb.wait_for_ready_state_complete()
        except Exception:
            pass

    sb.wait(3)
    print("[Zula] Login flow complete; lobby expected.")
    return True


# ───────────────────────────────────────────────────────────
# Main UC-based flow
# ───────────────────────────────────────────────────────────
async def zula_uc(ctx, channel: discord.abc.Messageable):
    """
    Zula via SeleniumBase UC.

    Main fix:
    - Do not click generic Collect buttons.
    - Scan page text for claimed/checkout states first.
    - Find the daily reward card/package.
    - Click only the Collect/Claim button inside that daily package.
    - After clicking, send "Zula Daily Bonus Claimed!" only if the page confirms daily claimed.
    - If it sees CHECKOUT/payment text, it treats that as a false-positive purchase path.
    """
    await channel.send("Launching **Zula** (UC)…")

    if ":" not in ZULA_CRED:
        await channel.send("❌ Missing `ZULA` as 'email:password' in your .env.")
        return

    username, password = ZULA_CRED.split(":", 1)

    try:
        with SB(uc=True, headed=True) as sb:
            try:
                if not _login_zula(sb, username, password):
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Login/auth failed. Not marking as claimed.",
                        "zula_auth_failed",
                    )
                    return

                _close_popups(sb)

                if not _open_rewards_modal(sb):
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Rewards button not found. Not marking as claimed.",
                        "zula_rewards_not_found",
                    )
                    return

                sb.wait(5)
                print("[Zula] Rewards/Coin Store modal should be open.")

                pre = _wait_for_state(
                    sb,
                    wanted=("daily_claimed", "checkout", "rewards_modal"),
                    timeout=6,
                    step=1,
                )

                if pre["status"] == "checkout":
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Checkout/payment page detected before claim. Not marking as claimed.",
                        "zula_checkout_pre",
                    )
                    return

                if pre["status"] == "daily_claimed":
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Bonus unavailable — today's bonus is already claimed.",
                        "zula_already_claimed",
                    )
                    return

                candidate = _find_daily_claim_candidate(sb)

                if not candidate:
                    sb.wait(2)
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

                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] No safe daily bonus claim button found. Not marking as claimed.",
                        "zula_no_safe_candidate",
                    )
                    return

                print(f"[Zula] Selected claim candidate: {candidate}")

                if not _click_candidate(sb, candidate.get("candidateId", "")):
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Found a daily bonus candidate but could not click it. Not marking as claimed.",
                        "zula_candidate_click_failed",
                    )
                    return

                sb.wait(2)

                final = _wait_for_state(
                    sb,
                    wanted=("daily_claimed", "checkout"),
                    timeout=10,
                    step=1,
                )

                if final["status"] == "checkout":
                    print(f"[Zula] False-positive prevented: {final}")
                    await _send_status_shot(
                        sb,
                        channel,
                        "[Zula] Click led to checkout/payment, so this was not counted as a daily bonus claim.",
                        "zula_checkout_false_positive",
                    )
                    return

                if final["status"] == "daily_claimed":
                    await _send_post_claim(
                        sb,
                        channel,
                        "zula_claimed.png",
                        "Zula Daily Bonus Claimed!",
                    )
                    print("[Zula] Claimed successfully and verified.")
                    return

                print(f"[Zula] Claim click was not verified. Final state: {final}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Claim click happened, but the page did not confirm a daily claim. Not marking as claimed.",
                    "zula_unverified",
                )
                return

            except Exception as e:
                print(f"[Zula][ERROR] Exception during automation: {e}")
                await _send_status_shot(
                    sb,
                    channel,
                    "[Zula] Error during automation. Not marking as claimed.",
                    "zula_error",
                )
                return

    except Exception as e:
        print(f"[Zula][ERROR] Could not start SeleniumBase UC session: {e}")
        await channel.send("[Zula] Browser/session error. Not marking as claimed.")