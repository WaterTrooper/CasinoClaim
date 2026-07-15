# Drake Hooks + WaterTrooper
# Casino Claim 3
# Sportzino API (SeleniumBase UC)
# Robust login detection, cookie-consent handling, and conservative claim verification.

import os
import re
import tempfile
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import discord
from dotenv import load_dotenv
from seleniumbase import SB

load_dotenv()

# Expect "email:password" in SPORTZINO
SPORTZINO_CRED = os.getenv("SPORTZINO", "")

LOGIN_URL = "https://sportzino.com/login"
HOME_URL = "https://sportzino.com/"

EMAIL_LOCATORS: Tuple[str, ...] = (
    # Current stable attributes visible in DevTools.
    "input[data-testid='login-email-input']",
    "input[name='username']",
    "input[autocomplete='username']",
    "input[placeholder='@email']",
    "input[type='email']",
    # User-provided current absolute XPath.
    "/html/body/div[1]/div/main/div/div[3]/div/form/div[1]/div/input",
)

PASSWORD_LOCATORS: Tuple[str, ...] = (
    "input[data-testid='login-password-input']",
    "input[name='password']",
    "input[autocomplete='current-password']",
    "input[type='password']",
    # User-provided current absolute XPath.
    "/html/body/div[1]/div/main/div/div[3]/div/form/div[2]/div/input",
)



SUBMIT_LOCATORS: Tuple[str, ...] = (
    "button[data-testid='login-submit-button']",
    "button[type='submit']",
    "//button[normalize-space()='Log In']",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
)

COOKIE_ACCEPT_LOCATORS: Tuple[str, ...] = (
    "#onetrust-accept-btn-handler",
    "button[data-testid='cookie-accept-all']",
    "button[data-testid='accept-all-cookies']",
    "button[aria-label*='Accept All']",
    "button[aria-label*='accept all']",
    "//button[normalize-space()='Accept All']",
    "//button[normalize-space()='Allow All']",
    "//button[normalize-space()='Accept Cookies']",
    "//button[normalize-space()='I Agree']",
    "//button[normalize-space()='Agree']",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept all')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all')]",
)

COOKIE_MANAGE_LOCATORS: Tuple[str, ...] = (
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'manage cookies')]",
    "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'manage cookies')]",
    "button[data-testid='manage-cookies']",
)

CLAIMED_MARKERS: Tuple[str, ...] = (
    "TODAY'S BONUS IS CLAIMED",
    "TODAYS BONUS IS CLAIMED",
    "TODAY’S BONUS IS CLAIMED",
    "DAILY BONUS CLAIMED",
    "BONUS IS CLAIMED",
    "ALREADY CLAIMED",
    "COME BACK TOMORROW",
    "SEE YOU TOMORROW",
)

SUCCESS_MARKERS: Tuple[str, ...] = (
    "CONGRATULATIONS",
    "DAILY BONUS CLAIMED",
    "TODAY'S BONUS IS CLAIMED",
    "TODAYS BONUS IS CLAIMED",
    "START PLAYING",
    "REWARD CLAIMED",
    "BONUS CLAIMED",
)

LOGIN_ERROR_MARKERS: Tuple[str, ...] = (
    "INVALID EMAIL",
    "INVALID PASSWORD",
    "INVALID CREDENTIALS",
    "EMAIL OR PASSWORD",
    "INCORRECT PASSWORD",
    "ACCOUNT NOT FOUND",
    "PLEASE COMPLETE THE CAPTCHA",
    "CAPTCHA IS REQUIRED",
    "SOMETHING WENT WRONG",
    "TOO MANY ATTEMPTS",
)

CHECKOUT_MARKERS: Tuple[str, ...] = (
    "CHECKOUT",
    "ORDER SUMMARY",
    "PAYMENT METHOD",
    "TOTAL AMOUNT TO PAY",
    "CREDIT/DEBIT",
    "PAY USING",
)


# ───────────────────────────────────────────────────────────
# Generic helpers
# ───────────────────────────────────────────────────────────

def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\xa0", " ").replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", value).strip()


def _up(value: Any) -> str:
    return _norm(value).upper()


def _contains_any(text: Any, markers: Iterable[str]) -> bool:
    upper = _up(text)
    return any(marker in upper for marker in markers)


def _first_marker(text: Any, markers: Iterable[str]) -> str:
    upper = _up(text)
    for marker in markers:
        if marker in upper:
            return marker
    return ""


def _short(text: Any, limit: int = 180) -> str:
    text = _norm(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _safe_js(sb: SB, script: str, *args, default=None):
    try:
        return sb.execute_script(script, *args)
    except Exception as exc:
        print(f"[Sportzino][JS WARN] {exc}")
        return default


def _page_snapshot(sb: SB) -> Dict[str, str]:
    data = _safe_js(
        sb,
        """
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0'
                && rect.width > 0
                && rect.height > 0;
        };

        const visibleText = Array.from(document.querySelectorAll('body *'))
            .filter(visible)
            .map((el) => [
                el.innerText || el.textContent || el.value || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('title') || '',
                el.getAttribute('placeholder') || '',
                el.getAttribute('data-testid') || ''
            ].join(' '))
            .join(' ');

        return {
            url: window.location.href || '',
            title: document.title || '',
            body: document.body ? (document.body.innerText || document.body.textContent || '') : '',
            visibleText
        };
        """,
        default={},
    )

    if not isinstance(data, dict):
        return {"url": "", "title": "", "text": ""}

    return {
        "url": _norm(data.get("url", "")),
        "title": _norm(data.get("title", "")),
        "text": _norm(
            " ".join(
                [
                    data.get("title", ""),
                    data.get("body", ""),
                    data.get("visibleText", ""),
                ]
            )
        ),
    }


def _locator_visible(sb: SB, locator: str, timeout: float = 1.0) -> bool:
    try:
        sb.wait_for_element_visible(locator, timeout=timeout)
        return True
    except Exception:
        return False


def _first_visible_locator(
    sb: SB,
    locators: Sequence[str],
    timeout_each: float = 1.5,
) -> Optional[str]:
    for locator in locators:
        if _locator_visible(sb, locator, timeout=timeout_each):
            return locator
    return None


def _is_login_page(sb: SB) -> bool:
    snapshot = _page_snapshot(sb)
    url_upper = snapshot["url"].upper()

    email_visible = _first_visible_locator(sb, EMAIL_LOCATORS, timeout_each=0.2) is not None
    password_visible = _first_visible_locator(sb, PASSWORD_LOCATORS, timeout_each=0.2) is not None

    return (
        "/LOGIN" in url_upper
        or (email_visible and password_visible)
        or (
            "LOG IN WITH GOOGLE" in _up(snapshot["text"])
            and "PASSWORD" in _up(snapshot["text"])
        )
    )


def _is_authenticated(sb: SB) -> bool:
    snapshot = _page_snapshot(sb)
    upper = _up(snapshot["text"])
    url_upper = snapshot["url"].upper()

    if _is_login_page(sb):
        return False

    if any(token in url_upper for token in ("/AUTH/CALLBACK", "/CONNECT/AUTHORIZE")):
        return False

    authenticated_markers = (
        "COIN STORE",
        "FREE COINS",
        "GET COINS",
        "REWARDS",
        "MY ACCOUNT",
        "LOG OUT",
        "LOGOUT",
        "WALLET",
    )

    # The redirect away from /login and disappearance of both login inputs is
    # enough; marker text is an additional positive signal.
    return "/LOGIN" not in url_upper or any(marker in upper for marker in authenticated_markers)


# ───────────────────────────────────────────────────────────
# Screenshot helper
# ───────────────────────────────────────────────────────────

async def _send_screenshot(
    sb: SB,
    channel: discord.abc.Messageable,
    caption: str,
    prefix: str,
):
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".png", dir="/tmp")
    os.close(fd)

    try:
        sb.save_screenshot(path)
        await channel.send(caption, file=discord.File(path))
    except Exception:
        try:
            await channel.send(caption)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


# ───────────────────────────────────────────────────────────
# Click and typing helpers
# ───────────────────────────────────────────────────────────

def _force_click(sb: SB, locator: str, timeout: float = 8) -> bool:
    try:
        sb.wait_for_element_visible(locator, timeout=timeout)
    except Exception:
        return False

    try:
        sb.scroll_to(locator)
    except Exception:
        pass

    for mode in ("normal", "slow", "js", "directjs"):
        try:
            if mode == "normal":
                sb.click(locator, timeout=2)
            elif mode == "slow":
                sb.slow_click(locator)
            elif mode == "js":
                sb.js_click(locator)
            else:
                element = sb.find_element(locator)
                sb.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            continue

    return False


def _try_click_any(sb: SB, locators: Sequence[str], timeout_each: float = 5) -> bool:
    for locator in locators:
        if locator and _force_click(sb, locator, timeout=timeout_each):
            return True
    return False


def _fill_input(
    sb: SB,
    locators: Sequence[str],
    value: str,
    field_name: str,
) -> Optional[str]:
    """Find, clear, and fill the first visible matching input."""
    for locator in locators:
        try:
            sb.wait_for_element_visible(locator, timeout=3)

            try:
                sb.click(locator)
            except Exception:
                pass

            try:
                sb.press_keys(locator, "CTRL+A")
                sb.press_keys(locator, "BACKSPACE")
            except Exception:
                try:
                    sb.clear(locator)
                except Exception:
                    pass

            sb.type(locator, value)

            # Confirm that the browser actually received a value.
            actual = _safe_js(
                sb,
                "return arguments[0] ? (arguments[0].value || '') : '';",
                sb.find_element(locator),
                default="",
            )

            if _norm(actual):
                print(f"[Sportzino] Filled {field_name} using: {locator}")
                return locator

        except Exception:
            continue

    print(f"[Sportzino] Could not fill {field_name} using any known locator.")
    return None


# ───────────────────────────────────────────────────────────
# Cookie handling
# ───────────────────────────────────────────────────────────

def _js_click_cookie_accept(sb: SB) -> bool:
    return bool(
        _safe_js(
            sb,
            r"""
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && style.opacity !== '0'
                    && rect.width > 0
                    && rect.height > 0;
            };

            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const preferred = [
                'accept all',
                'allow all',
                'accept cookies',
                'i agree',
                'agree and continue',
                'save and accept',
                'accept'
            ];

            const elements = Array.from(
                document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]')
            ).filter(visible);

            for (const phrase of preferred) {
                const match = elements.find((el) => {
                    const text = normalize([
                        el.innerText,
                        el.textContent,
                        el.value,
                        el.getAttribute('aria-label'),
                        el.getAttribute('title')
                    ].join(' '));
                    return text === phrase || text.includes(phrase);
                });

                if (match) {
                    match.scrollIntoView({block: 'center'});
                    match.click();
                    return true;
                }
            }

            return false;
            """,
            default=False,
        )
    )


def _neutralize_cookie_overlay(sb: SB) -> bool:
    """
    Last-resort visual/interception fallback.

    This does not pretend consent was accepted. It only disables a fixed cookie
    overlay after real Accept/Allow attempts fail, so the login controls remain
    clickable.
    """
    return bool(
        _safe_js(
            sb,
            r"""
            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const nodes = Array.from(document.querySelectorAll('div, section, aside'));
            let changed = false;

            for (const node of nodes) {
                const text = normalize(node.innerText || node.textContent || '');
                if (!text) continue;

                const looksLikeCookie =
                    text.includes('we value your privacy') ||
                    text.includes('manage cookies') ||
                    text.includes('privacy policy') && text.includes('cookies');

                if (!looksLikeCookie) continue;

                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                const overlayLike =
                    style.position === 'fixed' ||
                    style.position === 'sticky' ||
                    Number(style.zIndex || 0) > 10 ||
                    (rect.width > 250 && rect.height > 100);

                if (overlayLike) {
                    node.style.setProperty('display', 'none', 'important');
                    node.style.setProperty('pointer-events', 'none', 'important');
                    changed = true;
                }
            }

            return changed;
            """,
            default=False,
        )
    )


def _handle_cookie_consent(sb: SB) -> bool:
    """Accept the cookie banner when possible; neutralize it only as fallback."""
    accepted = _try_click_any(sb, COOKIE_ACCEPT_LOCATORS, timeout_each=1.5)

    if not accepted:
        accepted = _js_click_cookie_accept(sb)

    if accepted:
        print("[Sportzino] Cookie consent accepted.")
        sb.wait(0.5)
        return True

    # The visible login screenshot shows a Manage Cookies control. Open it and
    # search again for the actual Accept All option.
    managed = _try_click_any(sb, COOKIE_MANAGE_LOCATORS, timeout_each=1.5)
    if managed:
        print("[Sportzino] Opened cookie settings.")
        sb.wait(0.6)

        accepted = _try_click_any(sb, COOKIE_ACCEPT_LOCATORS, timeout_each=2)
        if not accepted:
            accepted = _js_click_cookie_accept(sb)

        if accepted:
            print("[Sportzino] Cookie consent accepted from settings.")
            sb.wait(0.5)
            return True

    neutralized = _neutralize_cookie_overlay(sb)
    if neutralized:
        print("[Sportzino] Cookie overlay neutralized after accept controls were unavailable.")

    return neutralized


# ───────────────────────────────────────────────────────────
# Login flow
# ───────────────────────────────────────────────────────────

def _captcha_looks_ready(sb: SB) -> bool:
    snapshot = _page_snapshot(sb)
    upper = _up(snapshot["text"])

    return (
        "SUCCESS!" in upper
        or "VERIFICATION SUCCESSFUL" in upper
        or "CHALLENGE PASSED" in upper
        or "CLOUDFLARE" not in upper
    )


def _submit_login(sb: SB, password_locator: str) -> bool:
    # Explicit button is preferred because the current page has a normal form
    # and Enter can be swallowed by the Cloudflare widget.
    if _try_click_any(sb, SUBMIT_LOCATORS, timeout_each=4):
        print("[Sportzino] Login form submitted with button.")
        return True

    try:
        sb.press_keys(password_locator, "\n")
        print("[Sportzino] Login form submitted with Enter fallback.")
        return True
    except Exception:
        return False


def _wait_for_authentication(sb: SB, timeout: float = 35) -> Dict[str, str]:
    """Wait for a real redirect away from the login form."""
    step = 1.0
    loops = max(1, int(timeout / step))
    last = {"status": "unknown", "reason": "No state yet", "evidence": ""}

    for index in range(loops):
        _handle_cookie_consent(sb)
        snapshot = _page_snapshot(sb)
        text = snapshot["text"]

        error_hit = _first_marker(text, LOGIN_ERROR_MARKERS)
        if error_hit:
            return {
                "status": "login_error",
                "reason": "The login page displayed an error",
                "evidence": error_hit,
            }

        if _is_authenticated(sb):
            return {
                "status": "authenticated",
                "reason": "Login form disappeared and browser left the login route",
                "evidence": snapshot["url"],
            }

        last = {
            "status": "login_pending",
            "reason": "Still on the login page",
            "evidence": snapshot["url"],
        }

        # A delayed Cloudflare completion can enable the same button after the
        # first click. Retry once without refilling the credentials.
        if index in (7, 15) and _captcha_looks_ready(sb):
            _try_click_any(sb, SUBMIT_LOCATORS, timeout_each=2)

        sb.wait(step)

    return last


def _login(sb: SB, username: str, password: str) -> Dict[str, str]:
    sb.uc_open_with_reconnect(LOGIN_URL, 4)
    sb.wait_for_ready_state_complete()
    print("[Sportzino] Login page loaded.")

    _handle_cookie_consent(sb)

    email_locator = _fill_input(sb, EMAIL_LOCATORS, username, "email")
    password_locator = _fill_input(sb, PASSWORD_LOCATORS, password, "password")

    if not email_locator or not password_locator:
        return {
            "status": "login_fields_missing",
            "reason": "The current email/password inputs could not be filled",
            "evidence": f"email={bool(email_locator)} password={bool(password_locator)}",
        }

    # Give Cloudflare a moment to initialize after the inputs are populated.
    sb.wait(1.5)

    try:
        sb.uc_gui_click_captcha()
        print("[Sportzino] Cloudflare captcha click attempted.")
    except Exception as exc:
        print(f"[Sportzino] Captcha click was unnecessary or unavailable: {exc}")

    # Wait briefly for the visible "Success!" state shown in the supplied
    # screenshot, but do not require it because Cloudflare can be invisible.
    for _ in range(12):
        if _captcha_looks_ready(sb):
            break
        sb.wait(0.5)

    _handle_cookie_consent(sb)

    if not _submit_login(sb, password_locator):
        return {
            "status": "submit_failed",
            "reason": "Could not click or submit the login form",
            "evidence": "No submit method succeeded",
        }

    return _wait_for_authentication(sb, timeout=35)


# ───────────────────────────────────────────────────────────
# Lobby/rewards helpers
# ───────────────────────────────────────────────────────────

def _close_popups_before_rewards(sb: SB):
    popup_locators = (
        "/html/body/div[3]/div/div[1]/div/div/div/div[1]/div[2]/button",
        "/html/body/div[3]/div/div[1]/div/div/button",
        "/html/body/div[4]/div/div[1]/div/div/button",
        "/html/body/div[5]/div/div[1]/div/div/button",
        "/html/body/div[6]/div/div[1]/div/div/div/div[2]/button",
        "//button[@aria-label='Close' or @aria-label='close']",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dismiss')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it')]",
        "//div[contains(@class,'modal')]//button[contains(@class,'close')]",
    )

    closed = 0
    for _ in range(3):
        if _try_click_any(sb, popup_locators, timeout_each=1.5):
            closed += 1
            sb.wait(0.4)
        else:
            break

    if closed:
        print(f"[Sportzino] Closed {closed} lobby popup(s).")

    _handle_cookie_consent(sb)

    try:
        sb.press_keys("body", "ESCAPE")
    except Exception:
        pass


def _open_rewards(sb: SB) -> bool:
    locators = (
        # Existing known header locations.
        "/html/body/div[1]/div/nav/div/div[4]/div[1]/button",
        "/html/body/div[1]/div[1]/div/nav/div/div[4]/div[1]/button",
        # Current text and accessible-name fallbacks.
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'coin store')]",
        "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'coin store')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'free coins')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get coins')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'rewards')]",
        "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'free coins')]",
        "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get coins')]",
        "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'rewards')]",
        "//*[@aria-label and (contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'coin') or contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reward'))]",
        "//*[@title and (contains(translate(@title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'coin') or contains(translate(@title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reward'))]",
    )

    if _try_click_any(sb, locators, timeout_each=4):
        return True

    # Last fallback: score visible clickable controls by their own and nearby text.
    candidate_id = _safe_js(
        sb,
        r"""
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0'
                && rect.width > 0
                && rect.height > 0;
        };

        const normalize = (value) => (value || '')
            .replace(/\s+/g, ' ')
            .trim()
            .toLowerCase();

        const candidates = Array.from(
            document.querySelectorAll('button, a, [role="button"]')
        ).filter(visible).map((el, index) => {
            const parent = el.closest('header, nav, section, article') || el.parentElement;
            const own = normalize([
                el.innerText,
                el.textContent,
                el.getAttribute('aria-label'),
                el.getAttribute('title')
            ].join(' '));
            const context = normalize(parent ? (parent.innerText || parent.textContent || '') : '');
            const combined = `${own} ${context}`;
            let score = 0;

            if (own.includes('coin store')) score += 180;
            if (own.includes('free coins')) score += 170;
            if (own.includes('get coins')) score += 160;
            if (own.includes('rewards')) score += 140;
            if (combined.includes('coin store')) score += 55;
            if (combined.includes('free coins')) score += 50;
            if (combined.includes('rewards')) score += 40;
            if (combined.includes('log in') || combined.includes('sign up')) score -= 300;

            const id = `sportzino-reward-${index}`;
            el.setAttribute('data-sportzino-reward-id', id);
            return {id, score};
        }).sort((a, b) => b.score - a.score);

        return candidates.length && candidates[0].score >= 120
            ? candidates[0].id
            : '';
        """,
        default="",
    )

    if not candidate_id:
        return False

    return _force_click(sb, f"[data-sportzino-reward-id='{candidate_id}']", timeout=2)


def _current_state(sb: SB) -> Dict[str, str]:
    snapshot = _page_snapshot(sb)
    text = snapshot["text"]

    checkout_hit = _first_marker(text, CHECKOUT_MARKERS)
    if checkout_hit:
        return {
            "status": "checkout",
            "reason": "Checkout/payment interface detected",
            "evidence": checkout_hit,
        }

    if _is_login_page(sb):
        return {
            "status": "login",
            "reason": "Login page is still visible",
            "evidence": snapshot["url"],
        }

    claimed_hit = _first_marker(text, CLAIMED_MARKERS)
    if claimed_hit:
        return {
            "status": "claimed",
            "reason": "Page reports that the daily bonus is already claimed",
            "evidence": claimed_hit,
        }

    success_hit = _first_marker(text, SUCCESS_MARKERS)
    if success_hit:
        return {
            "status": "success",
            "reason": "Claim-success text detected",
            "evidence": success_hit,
        }

    upper = _up(text)
    if any(marker in upper for marker in ("COIN STORE", "FREE COINS", "REWARDS", "DAILY BONUS")):
        return {
            "status": "rewards",
            "reason": "Rewards/coins interface detected",
            "evidence": "REWARDS UI",
        }

    return {
        "status": "unknown",
        "reason": "Page state did not match a known condition",
        "evidence": _short(text, 120),
    }


def _click_daily_collect(sb: SB) -> bool:
    locators = (
        "/html/body/div[1]/div[1]/div/div/div[2]/div[2]/div[2]/div[1]/div/div[3]/div/div[1]/button",
        "/html/body/div[5]/div/div[1]/div/div/div[2]/div[2]/div[2]/div[1]/div/div[3]/div/div[1]/button",
        "/html/body/div[4]/div/div[1]/div/div/div[2]/div[2]/div[2]/div[1]/div/div[3]/div/div[1]/button",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect') and not(@disabled) and not(@aria-disabled='true')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim') and not(@disabled) and not(@aria-disabled='true')]",
    )

    return _try_click_any(sb, locators, timeout_each=4)


def _wait_for_claim_result(sb: SB, timeout: float = 12) -> Dict[str, str]:
    step = 0.5
    loops = max(1, int(timeout / step))
    last = _current_state(sb)

    for _ in range(loops):
        last = _current_state(sb)
        print(
            f"[Sportzino] Claim state={last['status']} "
            f"reason={last['reason']} evidence={last['evidence']}"
        )

        if last["status"] in ("success", "claimed", "checkout", "login"):
            return last

        sb.wait(step)

    return last


# ───────────────────────────────────────────────────────────
# Main UC-based flow
# ───────────────────────────────────────────────────────────

async def Sportzino(ctx, driver, channel: discord.abc.Messageable):
    """
    Sportzino via SeleniumBase UC.

    Important changes:
    - Uses the current data-testid/name attributes plus the supplied XPaths.
    - Accepts or neutralizes the cookie popup before interacting with the form.
    - Waits for a confirmed redirect away from /login before looking for Rewards.
    - Never reports "Rewards section not found" while the login form is still open.
    - Conservatively verifies claim success after clicking Collect/Claim.
    """
    del ctx, driver  # Kept in the public signature for compatibility with the bot.

    if ":" not in SPORTZINO_CRED:
        await channel.send("[Sportzino][ERROR] Missing SPORTZINO as 'email:password' in .env")
        return

    username, password = SPORTZINO_CRED.split(":", 1)

    try:
        with SB(uc=True, headed=True) as sb:
            login_result = _login(sb, username, password)
            print(f"[Sportzino] Login result: {login_result}")

            if login_result["status"] != "authenticated":
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Login did not complete — "
                        f"{login_result['reason']}. Not attempting a claim."
                    ),
                    "sportzino_login_failed",
                )
                return

            # Normalize to the main lobby only after authentication has been
            # positively confirmed. The existing session cookie is retained.
            current_url = _page_snapshot(sb)["url"]
            if not current_url or any(
                token in current_url.lower()
                for token in ("/auth/callback", "/connect/authorize", "/login")
            ):
                sb.open(HOME_URL)

            sb.wait_for_ready_state_complete()
            sb.wait(4)
            _handle_cookie_consent(sb)
            _close_popups_before_rewards(sb)

            # A session-expiration redirect must be caught before rewards logic.
            if _is_login_page(sb):
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Login session did not persist after redirect. Not attempting a claim.",
                    "sportzino_session_lost",
                )
                return

            opened_rewards = _open_rewards(sb)

            if not opened_rewards:
                state = _current_state(sb)
                print(f"[Sportzino] Could not open rewards. Current state: {state}")

                if state["status"] == "login":
                    caption = "[Sportzino] Login expired before Rewards could open."
                else:
                    caption = "[Sportzino] Rewards/Coins section not found after confirmed login."

                await _send_screenshot(
                    sb,
                    channel,
                    caption,
                    "sportzino_rewards_missing",
                )
                return

            sb.wait(5)
            _handle_cookie_consent(sb)
            print("[Sportzino] Rewards UI should now be open.")

            pre_state = _current_state(sb)
            print(f"[Sportzino] Pre-claim state: {pre_state}")

            if pre_state["status"] == "login":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Login expired before the claim could run.",
                    "sportzino_login_expired",
                )
                return

            if pre_state["status"] == "checkout":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Checkout/payment page detected. Not marking as claimed.",
                    "sportzino_checkout_pre",
                )
                return

            if pre_state["status"] == "claimed":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Bonus unavailable — today's bonus is already claimed.",
                    "sportzino_already_claimed",
                )
                return

            clicked = _click_daily_collect(sb)
            if not clicked:
                state = _current_state(sb)
                caption = (
                    "[Sportzino] Bonus unavailable — today's bonus is already claimed."
                    if state["status"] == "claimed"
                    else "[Sportzino] No enabled daily Collect/Claim button was found."
                )
                await _send_screenshot(
                    sb,
                    channel,
                    caption,
                    "sportzino_no_claim",
                )
                return

            result = _wait_for_claim_result(sb, timeout=12)

            if result["status"] in ("success", "claimed"):
                await _send_screenshot(
                    sb,
                    channel,
                    "Sportzino Daily Bonus Claimed!",
                    "sportzino_claimed",
                )
                print(f"[Sportzino] Claim verified: {result}")
                return

            if result["status"] == "checkout":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Claim click opened checkout/payment. Not marking as claimed.",
                    "sportzino_checkout_false_positive",
                )
                return

            if result["status"] == "login":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Login expired immediately after the claim click. Not marking as claimed.",
                    "sportzino_post_click_login",
                )
                return

            await _send_screenshot(
                sb,
                channel,
                "[Sportzino] Claim click happened, but the page did not confirm the daily claim.",
                "sportzino_unverified",
            )

    except Exception as exc:
        print(f"[Sportzino][ERROR] Exception during automation: {exc}")
        await channel.send(f"[Sportzino][ERROR] Exception during automation: {exc}")
