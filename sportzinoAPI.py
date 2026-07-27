# Drake Hooks + WaterTrooper
# Casino Claim 3
# Sportzino API (SeleniumBase UC)
# Simple login, intelligent Progressive Daily Bonus candidacy, and verified claiming.

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
    # Exact current Sportzino login field from the supplied DevTools markup.
    "#emailAddress",
    "input#emailAddress",
    "input[data-testid='login-email-input']",
    "input[name='username']",
    "input[autocomplete='username']",
    "input[placeholder='@email']",
    "input[type='email']",
    # Absolute XPath is retained only as a final fallback.
    "/html/body/div[1]/div/main/div/div[3]/div/form/div[1]/div/input",
)

PASSWORD_LOCATORS: Tuple[str, ...] = (
    # Exact current Sportzino login field from the supplied DevTools markup.
    "#password",
    "input#password",
    "input[data-testid='login-password-input']",
    "input[name='password']",
    "input[autocomplete='current-password']",
    "input[type='password']",
    # Absolute XPath is retained only as a final fallback.
    "/html/body/div[1]/div/main/div/div[3]/div/form/div[2]/div/input",
)

SUBMIT_LOCATORS: Tuple[str, ...] = (
    # Scope the click to the actual login form so another page button cannot win.
    "form.login-form .login-form-login-button-container button",
    ".login-form-login-button-container button",
    "form.login-form button[type='submit']",
    "form.login-form button[data-testid='login-submit-button']",
    "button[data-testid='login-submit-button']",
    "//form[contains(@class,'login-form')]//button[normalize-space()='Log In']",
    "//form[contains(@class,'login-form')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in')]",
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

    # Visible login controls always override URL/text guesses.
    email_visible = _first_visible_locator(sb, EMAIL_LOCATORS, timeout_each=0.15) is not None
    password_visible = _first_visible_locator(sb, PASSWORD_LOCATORS, timeout_each=0.15) is not None
    if email_visible or password_visible:
        return False

    if any(
        token in url_upper
        for token in (
            "/LOGIN",
            "/AUTH/CALLBACK",
            "/CONNECT/AUTHORIZE",
            "/ERROR",
            "/ACCESSDENIED",
        )
    ):
        return False

    authenticated_markers = (
        "COIN STORE",
        "GET COINS",
        "REWARDS",
        "MY ACCOUNT",
        "LOG OUT",
        "LOGOUT",
        "WALLET",
    )

    if any(marker in upper for marker in authenticated_markers):
        return True

    # Sportzino normally redirects to the lobby after a successful login. A
    # non-login Sportzino URL with no visible login fields is therefore valid.
    return "SPORTZINO.COM" in url_upper and "/LOGIN" not in url_upper


# ───────────────────────────────────────────────────────────
# Screenshot helper
# ───────────────────────────────────────────────────────────

async def _send_screenshot(
    sb: SB,
    channel: discord.abc.Messageable,
    caption: str,
    prefix: str,
    discord_message: Optional[str] = None,
):
    """
    Print all status/debug information to the worker console.

    When discord_message is provided, send that exact final status to Discord,
    followed by the screenshot. Other internal details remain console-only.
    """
    print(caption)

    fd, path = tempfile.mkstemp(
        prefix=f"{prefix}_",
        suffix=".png",
        dir="/tmp",
    )
    os.close(fd)

    try:
        sb.save_screenshot(path)

        if discord_message:
            await channel.send(discord_message)

        await channel.send(file=discord.File(path))
    except Exception as error:
        print(f"[Sportzino][SCREENSHOT ERROR] {error}")
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as cleanup_error:
            print(
                "[Sportzino][SCREENSHOT CLEANUP ERROR] "
                f"{cleanup_error}"
            )


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
    """Fill the first visible input without scrolling the page."""
    for locator in locators:
        try:
            sb.wait_for_element_visible(locator, timeout=4)
            element = sb.find_element(locator)

            # React/Sentry controlled inputs can ignore a plain JS assignment.
            # Use the native HTMLInputElement setter and dispatch the same events
            # a real user action generates.
            actual = _safe_js(
                sb,
                r"""
                const el = arguments[0];
                const value = arguments[1];
                if (!el) return '';

                el.focus({preventScroll: true});
                const descriptor = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype,
                    'value'
                );
                descriptor.set.call(el, '');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                descriptor.set.call(el, value);
                el.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    inputType: 'insertText',
                    data: value
                }));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
                return el.value || '';
                """,
                element,
                value,
                default="",
            )

            # Selenium keystrokes are a fallback if the framework rewrites the
            # value after the native setter/events above.
            if actual != value:
                try:
                    element.click()
                    element.clear()
                    element.send_keys(value)
                except Exception:
                    pass

                actual = _safe_js(
                    sb,
                    "return arguments[0] ? (arguments[0].value || '') : '';",
                    element,
                    default="",
                )

            if actual == value:
                print(
                    f"[Sportzino] Filled {field_name} using {locator} "
                    f"({len(value)} characters)."
                )
                return locator

        except Exception as exc:
            print(f"[Sportzino] {field_name} locator failed ({locator}): {exc}")

    print(f"[Sportzino] Could not fill {field_name} using any known locator.")
    return None


# ───────────────────────────────────────────────────────────
# Cookie handling
# ───────────────────────────────────────────────────────────

def _js_click_cookie_accept(sb: SB) -> bool:
    """Click Accept only inside a genuine cookie dialog/banner overlay."""
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
                    && rect.height > 0
                    && rect.bottom > 0
                    && rect.top < window.innerHeight;
            };

            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const isOverlay = (node) => {
                if (!visible(node)) return false;
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                const role = normalize(node.getAttribute('role'));
                const cookieText = normalize([
                    node.innerText,
                    node.textContent,
                    node.getAttribute('aria-label'),
                    node.id,
                    node.className
                ].join(' '));

                const mentionsCookies =
                    cookieText.includes('cookie') ||
                    cookieText.includes('privacy preferences') ||
                    cookieText.includes('we value your privacy');

                const positionedOverlay =
                    style.position === 'fixed' ||
                    style.position === 'sticky' ||
                    role === 'dialog' ||
                    role === 'alertdialog';

                const overlapsViewport =
                    rect.bottom > 0 &&
                    rect.top < window.innerHeight &&
                    rect.right > 0 &&
                    rect.left < window.innerWidth;

                return mentionsCookies && positionedOverlay && overlapsViewport;
            };

            const roots = Array.from(new Set([
                ...document.querySelectorAll(
                    '#onetrust-banner-sdk, #onetrust-pc-sdk, ' +
                    '#CybotCookiebotDialog, .cky-consent-container, ' +
                    '.osano-cm-window, [role="dialog"], [role="alertdialog"], ' +
                    '[data-testid*="cookie" i], [id*="cookie" i], [class*="cookie" i]'
                ),
                ...Array.from(document.querySelectorAll('div, section, aside')).filter(isOverlay)
            ])).filter(isOverlay);

            const preferred = [
                'accept all',
                'allow all',
                'accept cookies',
                'agree and continue',
                'save and accept',
                'i agree',
                'accept'
            ];

            for (const root of roots) {
                // Buttons only. Never click a footer/link named Manage Cookies.
                const controls = Array.from(root.querySelectorAll(
                    'button, input[type="button"], input[type="submit"], [role="button"]'
                )).filter(visible);

                for (const phrase of preferred) {
                    const match = controls.find((el) => {
                        const text = normalize([
                            el.innerText,
                            el.textContent,
                            el.value,
                            el.getAttribute('aria-label'),
                            el.getAttribute('title')
                        ].join(' '));
                        return text === phrase || text.startsWith(`${phrase} `);
                    });

                    if (match) {
                        match.click();
                        return true;
                    }
                }
            }

            return false;
            """,
            default=False,
        )
    )


def _neutralize_cookie_overlay(sb: SB) -> bool:
    """Hide only a fixed/sticky cookie overlay that blocks the login form."""
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
                    && rect.width > 0
                    && rect.height > 0
                    && rect.bottom > 0
                    && rect.top < window.innerHeight;
            };

            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            let changed = false;
            const nodes = Array.from(document.querySelectorAll(
                '#onetrust-banner-sdk, #onetrust-pc-sdk, #CybotCookiebotDialog, ' +
                '.cky-consent-container, .osano-cm-window, [role="dialog"], ' +
                '[role="alertdialog"], div, section, aside'
            ));

            for (const node of nodes) {
                if (!visible(node)) continue;

                const style = window.getComputedStyle(node);
                const role = normalize(node.getAttribute('role'));
                const text = normalize([
                    node.innerText,
                    node.textContent,
                    node.getAttribute('aria-label'),
                    node.id,
                    node.className
                ].join(' '));

                const looksLikeCookie =
                    text.includes('cookie') ||
                    text.includes('privacy preferences') ||
                    text.includes('we value your privacy');

                const overlayLike =
                    style.position === 'fixed' ||
                    style.position === 'sticky' ||
                    role === 'dialog' ||
                    role === 'alertdialog';

                if (looksLikeCookie && overlayLike) {
                    node.style.setProperty('display', 'none', 'important');
                    node.style.setProperty('visibility', 'hidden', 'important');
                    node.style.setProperty('pointer-events', 'none', 'important');
                    changed = true;
                }
            }

            if (changed) {
                document.documentElement.style.removeProperty('overflow');
                document.body && document.body.style.removeProperty('overflow');
            }
            return changed;
            """,
            default=False,
        )
    )


def _handle_cookie_consent(sb: SB) -> bool:
    """Handle only an on-screen cookie overlay; never touch footer links."""
    accepted = _js_click_cookie_accept(sb)
    if accepted:
        print("[Sportzino] Cookie consent accepted from an active overlay.")
        sb.wait(0.4)
        return True

    neutralized = _neutralize_cookie_overlay(sb)
    if neutralized:
        print("[Sportzino] Blocking cookie overlay neutralized.")
        sb.wait(0.2)

    return neutralized


# ───────────────────────────────────────────────────────────
# Login flow
# ───────────────────────────────────────────────────────────

def _simple_login_button_enabled(sb: SB) -> bool:
    """Return True when the real Sportzino Log In button is enabled."""
    try:
        return bool(
            sb.execute_script(
                """
                const button = document.querySelector(
                    'form.login-form .login-form-login-button-container button'
                );

                return Boolean(
                    button &&
                    !button.disabled &&
                    button.getAttribute('aria-disabled') !== 'true'
                );
                """
            )
        )
    except Exception:
        return False


def _simple_click_login_button(sb: SB) -> bool:
    """
    Click only the Log In button inside Sportzino's email/password form.

    This intentionally follows the same simple approach used by the working
    American Luck login instead of changing React input values through JS.
    """
    locators = (
        "form.login-form .login-form-login-button-container button",
        ".login-form-login-button-container button",
        "//form[contains(@class,'login-form')]"
        "//div[contains(@class,'login-form-login-button-container')]//button",
        "//form[contains(@class,'login-form')]"
        "//button[normalize-space()='Log In']",
    )

    for locator in locators:
        try:
            sb.wait_for_element_visible(locator, timeout=4)
            sb.click(locator)
            print(f"[Sportzino] Clicked Log In using: {locator}")
            return True
        except Exception as error:
            print(
                f"[Sportzino] Login click locator failed "
                f"({locator}): {error}"
            )

    # Same hard-click fallback style used by American Luck.
    try:
        button = sb.find_element(
            "form.login-form .login-form-login-button-container button"
        )
        sb.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            button,
        )
        sb.wait(0.3)
        button.click()
        print("[Sportzino] Clicked Log In with WebElement fallback.")
        return True
    except Exception:
        pass

    try:
        button = sb.find_element(
            "form.login-form .login-form-login-button-container button"
        )
        sb.execute_script("arguments[0].click();", button)
        print("[Sportzino] Clicked Log In with JS fallback.")
        return True
    except Exception:
        return False


def _simple_login_error(sb: SB) -> str:
    snapshot = _page_snapshot(sb)
    return _first_marker(snapshot["text"], LOGIN_ERROR_MARKERS)


def _login(sb: SB, username: str, password: str) -> Dict[str, str]:
    """
    Simple Sportzino login modeled after the working American Luck login:

    1. Open the login page.
    2. Type directly into #emailAddress and #password with SeleniumBase.
    3. Click the Cloudflare challenge when needed.
    4. Click the form's real Log In button.
    5. Wait for the login form to disappear or the URL to leave /login.

    No JavaScript value injection is used for the credentials.
    """
    sb.uc_open_with_reconnect(LOGIN_URL, 8)

    try:
        sb.wait_for_ready_state_complete()
    except Exception:
        pass

    sb.wait(2)
    print("[Sportzino] Login page loaded.")

    # Handle only a real on-screen cookie overlay. This cannot click the
    # footer's Manage Cookies link.
    _handle_cookie_consent(sb)

    try:
        sb.wait_for_element_visible("#emailAddress", timeout=20)
        sb.wait_for_element_visible("#password", timeout=20)
    except Exception as error:
        return {
            "status": "login_fields_missing",
            "reason": "The Sportzino email/password fields did not appear",
            "evidence": str(error),
        }

    # Keep the form in view before typing.
    try:
        sb.execute_script(
            """
            const email = document.querySelector('#emailAddress');
            if (email) {
                email.scrollIntoView({
                    block: 'center',
                    inline: 'nearest'
                });
            }
            """
        )
    except Exception:
        pass

    # IMPORTANT: Use normal SeleniumBase typing exactly like American Luck.
    # The previous JS/React setter could make the fields look populated while
    # Sportzino's form state still submitted blank values.
    try:
        sb.click("#emailAddress")
        sb.type("#emailAddress", username)
        print(
            "[Sportzino] Typed email directly into #emailAddress "
            f"({len(username)} characters)."
        )

        sb.click("#password")
        sb.type("#password", password)
        print(
            "[Sportzino] Typed password directly into #password "
            f"({len(password)} characters)."
        )
    except Exception as error:
        return {
            "status": "login_typing_failed",
            "reason": "Could not type into the Sportzino login fields",
            "evidence": str(error),
        }

    # Confirm the browser truly contains the credentials before touching
    # Cloudflare or the submit button.
    try:
        typed_email = sb.get_attribute("#emailAddress", "value") or ""
        typed_password = sb.get_attribute("#password", "value") or ""
    except Exception:
        typed_email = ""
        typed_password = ""

    print(
        "[Sportzino] Field check before captcha: "
        f"email_chars={len(typed_email)} "
        f"password_chars={len(typed_password)}"
    )

    if typed_email != username or typed_password != password:
        return {
            "status": "login_fields_rejected",
            "reason": "Sportzino did not retain the typed credentials",
            "evidence": (
                f"email_chars={len(typed_email)} "
                f"password_chars={len(typed_password)}"
            ),
        }

    # Same Cloudflare handling sequence as American Luck.
    try:
        sb.uc_gui_click_captcha()
        print("[Sportzino] Cloudflare click attempted.")
    except Exception as error:
        print(
            "[Sportzino] Cloudflare click was unnecessary or unavailable: "
            f"{error}"
        )

    sb.wait(1.5)

    # Give Turnstile a reasonable amount of time to enable the form button.
    # Do not repeatedly submit or rewrite the fields.
    for second_half in range(30):
        if _simple_login_button_enabled(sb):
            break

        if second_half == 15:
            try:
                sb.uc_gui_click_captcha()
                print("[Sportzino] Retried the Cloudflare click once.")
            except Exception:
                pass

        sb.wait(0.5)

    # A GUI captcha interaction may have moved the viewport. Return only to
    # the login form, then click its exact Log In button.
    try:
        sb.execute_script(
            """
            const button = document.querySelector(
                'form.login-form .login-form-login-button-container button'
            );
            if (button) {
                button.scrollIntoView({
                    block: 'center',
                    inline: 'nearest'
                });
            }
            """
        )
    except Exception:
        pass

    # Verify that Cloudflare interaction did not erase the inputs.
    try:
        typed_email = sb.get_attribute("#emailAddress", "value") or ""
        typed_password = sb.get_attribute("#password", "value") or ""
    except Exception:
        typed_email = ""
        typed_password = ""

    print(
        "[Sportzino] Field check before submit: "
        f"email_chars={len(typed_email)} "
        f"password_chars={len(typed_password)}"
    )

    if typed_email != username or typed_password != password:
        # One simple normal-typing retry, still with no JS value injection.
        try:
            sb.type("#emailAddress", username)
            sb.type("#password", password)
            typed_email = sb.get_attribute("#emailAddress", "value") or ""
            typed_password = sb.get_attribute("#password", "value") or ""
        except Exception:
            pass

    if typed_email != username or typed_password != password:
        return {
            "status": "login_fields_lost",
            "reason": "The credentials disappeared before Log In was clicked",
            "evidence": (
                f"email_chars={len(typed_email)} "
                f"password_chars={len(typed_password)}"
            ),
        }

    if not _simple_click_login_button(sb):
        # Final American-Luck-style Enter fallback.
        try:
            sb.press_keys("#password", "\n")
            print("[Sportzino] Submitted login with Enter fallback.")
        except Exception as error:
            return {
                "status": "submit_failed",
                "reason": "Could not click or submit the Sportzino login form",
                "evidence": str(error),
            }

    # Wait for either success, a visible login error, or timeout.
    for index in range(60):
        error_hit = _simple_login_error(sb)
        if error_hit:
            return {
                "status": "login_error",
                "reason": "Sportzino displayed a login error",
                "evidence": error_hit,
            }

        if _is_authenticated(sb):
            snapshot = _page_snapshot(sb)
            return {
                "status": "authenticated",
                "reason": "Sportzino left the login page",
                "evidence": snapshot["url"],
            }

        # Some Turnstile forms accept the first click only after the token
        # settles. Retry the exact button once, without retyping anything.
        if index == 20 and _simple_login_button_enabled(sb):
            _simple_click_login_button(sb)

        sb.wait(0.5)

    snapshot = _page_snapshot(sb)
    return {
        "status": "login_pending",
        "reason": "Still on the login page after the simple login attempt",
        "evidence": snapshot["url"],
    }


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


def _rewards_dialog_open(sb: SB) -> bool:
    """Detect the visible Sportzino Coin Store / Claim Free Rewards dialog."""
    return bool(
        _safe_js(
            sb,
            r"""
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                return (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    style.opacity !== '0' &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const roots = Array.from(document.querySelectorAll(
                '.coin-store, .dialog-modal, [role="dialog"], ' +
                '[class*="coin-store" i]'
            )).filter(visible);

            return roots.some((root) => {
                const text = normalize(
                    root.innerText || root.textContent || ''
                );

                return (
                    text.includes('claim free rewards') ||
                    (
                        text.includes('coin store') &&
                        text.includes('purchase store packs')
                    )
                );
            });
            """,
            default=False,
        )
    )


def _visible_checkout_detected(sb: SB) -> bool:
    """
    Detect only a visible checkout/payment dialog.

    The previous implementation searched all body text, including hidden
    application markup, which falsely classified the open Coin Store as
    checkout.
    """
    return bool(
        _safe_js(
            sb,
            r"""
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                return (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    style.opacity !== '0' &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const normalize = (value) => (value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const roots = Array.from(document.querySelectorAll(
                '[role="dialog"], .dialog-modal, ' +
                '[class*="checkout" i], [class*="payment" i], ' +
                '[class*="order-summary" i]'
            )).filter(visible);

            return roots.some((root) => {
                const text = normalize(
                    root.innerText || root.textContent || ''
                );

                const isCoinStore =
                    text.includes('claim free rewards') &&
                    text.includes('purchase store packs');

                if (isCoinStore) return false;

                const checkoutSignals = [
                    'order summary',
                    'payment method',
                    'total amount to pay',
                    'credit/debit',
                    'pay using',
                    'complete purchase',
                    'billing information'
                ];

                return checkoutSignals.some(
                    (signal) => text.includes(signal)
                );
            });
            """,
            default=False,
        )
    )


def _daily_claim_candidates(sb: SB) -> list[Dict[str, Any]]:
    """
    Score every visible Collect/Claim button.

    The strongest signals come from Sportzino's stable DOM:
    - .coin-store-free-rewards-row-item.daily-bonus
    - .coin-store-collect-button
    - data-sentry-component="CoinStoreCollectButton"
    - nearby "Progressive Daily Bonus" / "Daily Bonus" text

    Purchase, Facebook, Google, and generic promotion controls receive large
    penalties. This keeps the bot from clicking an unrelated Collect button.
    """
    result = _safe_js(
        sb,
        r"""
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();

            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                style.opacity !== '0' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const normalize = (value) => (value || '')
            .replace(/\s+/g, ' ')
            .trim()
            .toLowerCase();

        const controls = Array.from(document.querySelectorAll(
            'button, [role="button"]'
        )).filter(visible);

        const candidates = [];

        controls.forEach((button, index) => {
            const ownText = normalize([
                button.innerText,
                button.textContent,
                button.getAttribute('aria-label'),
                button.getAttribute('title')
            ].join(' '));

            if (
                ownText !== 'collect' &&
                ownText !== 'claim' &&
                !ownText.startsWith('collect ') &&
                !ownText.startsWith('claim ')
            ) {
                return;
            }

            const disabled = Boolean(
                button.disabled ||
                button.getAttribute('aria-disabled') === 'true' ||
                normalize(button.className).includes('disabled')
            );

            const dailyRoot = button.closest(
                '.coin-store-free-rewards-row-item.daily-bonus, ' +
                '[class~="daily-bonus"], ' +
                '[class*="serial-daily-bonus" i]'
            );

            const rewardCard = button.closest(
                '.coin-store-free-rewards-card, ' +
                '.coin-store-free-rewards-row-item, ' +
                '[class*="free-rewards-card" i], ' +
                '[class*="free-rewards-row-item" i]'
            );

            const section = button.closest(
                '.coin-store-section, .coin-store-content, ' +
                '.coin-store, [role="dialog"]'
            );

            const localRoot =
                dailyRoot ||
                rewardCard ||
                button.parentElement ||
                button;

            const localText = normalize(
                localRoot.innerText ||
                localRoot.textContent ||
                ''
            );

            const sectionText = normalize(
                section
                    ? (
                        section.innerText ||
                        section.textContent ||
                        ''
                    )
                    : ''
            );

            const className = normalize(button.className);
            const component = normalize(
                button.getAttribute('data-sentry-component')
            );

            let score = 0;
            const reasons = [];

            if (ownText === 'collect') {
                score += 120;
                reasons.push('exact COLLECT text');
            } else if (ownText === 'claim') {
                score += 90;
                reasons.push('exact CLAIM text');
            } else {
                score += 45;
                reasons.push('claim-like text');
            }

            if (className.includes('coin-store-collect-button')) {
                score += 220;
                reasons.push('coin-store-collect-button class');
            }

            if (component === 'coinstorecollectbutton') {
                score += 220;
                reasons.push('CoinStoreCollectButton component');
            }

            if (dailyRoot) {
                score += 650;
                reasons.push('daily-bonus ancestor');
            }

            if (localText.includes('progressive daily bonus')) {
                score += 320;
                reasons.push('Progressive Daily Bonus context');
            } else if (localText.includes('daily bonus')) {
                score += 280;
                reasons.push('Daily Bonus context');
            }

            if (sectionText.includes('claim free rewards')) {
                score += 140;
                reasons.push('Claim Free Rewards section');
            }

            if (
                localText.includes('day 1') ||
                localText.includes('day 2') ||
                localText.includes('day 3') ||
                localText.includes('day 4') ||
                localText.includes('day 5') ||
                localText.includes('day 6') ||
                localText.includes('day 7')
            ) {
                score += 80;
                reasons.push('daily progression day');
            }

            if (
                localText.includes('facebook friendly') ||
                localText.includes('facebook')
            ) {
                score -= 700;
                reasons.push('Facebook penalty');
            }

            if (
                localText.includes('connect with google') ||
                localText.includes('google grab') ||
                localText.includes('google')
            ) {
                score -= 700;
                reasons.push('Google penalty');
            }

            if (
                localText.includes('purchase') ||
                localText.includes('buy now') ||
                localText.includes('checkout') ||
                /\$\s*\d/.test(localText)
            ) {
                score -= 800;
                reasons.push('purchase/payment penalty');
            }

            if (
                localText.includes('see more') &&
                !localText.includes('daily bonus')
            ) {
                score -= 150;
                reasons.push('generic promotion penalty');
            }

            if (disabled) {
                score -= 2000;
                reasons.push('disabled');
            }

            const candidateId =
                `sportzino-daily-claim-${Date.now()}-${index}`;

            button.setAttribute(
                'data-sportzino-daily-claim-id',
                candidateId
            );

            candidates.push({
                id: candidateId,
                score,
                text: ownText,
                localText: localText.slice(0, 260),
                className,
                component,
                disabled,
                hasDailyRoot: Boolean(dailyRoot),
                reasons
            });
        });

        candidates.sort((a, b) => b.score - a.score);
        return candidates;
        """,
        default=[],
    )

    return result if isinstance(result, list) else []


def _select_daily_claim_candidate(
    sb: SB,
) -> Optional[Dict[str, Any]]:
    candidates = _daily_claim_candidates(sb)

    if not candidates:
        print("[Sportzino] No visible Collect/Claim candidates found.")
        return None

    print("[Sportzino] Claim candidate ranking:")

    for index, candidate in enumerate(candidates[:8], start=1):
        print(
            f"  #{index} score={candidate.get('score')} "
            f"text={candidate.get('text')!r} "
            f"daily_root={candidate.get('hasDailyRoot')} "
            f"context={_short(candidate.get('localText', ''), 140)!r} "
            f"reasons={candidate.get('reasons')}"
        )

    best = candidates[0]
    best_score = int(best.get("score", 0))
    has_daily_root = bool(best.get("hasDailyRoot"))
    context = _up(best.get("localText", ""))

    context_is_daily = (
        "PROGRESSIVE DAILY BONUS" in context or
        "DAILY BONUS" in context
    )

    # Require both a very strong score and a direct daily-bonus signal.
    if best_score < 800 or not (has_daily_root or context_is_daily):
        print(
            "[Sportzino] Rejected the best candidate because it was not "
            "confidently tied to the Progressive Daily Bonus card."
        )
        return None

    # If two candidates are close, require the winner to have the explicit
    # daily-bonus ancestor. This avoids ambiguous global Collect buttons.
    if len(candidates) > 1:
        second_score = int(candidates[1].get("score", 0))

        if (
            best_score - second_score < 100 and
            not has_daily_root
        ):
            print(
                "[Sportzino] Rejected ambiguous claim candidates "
                f"(best={best_score}, second={second_score})."
            )
            return None

    return best


def _click_daily_collect(
    sb: SB,
) -> Optional[Dict[str, Any]]:
    candidate = _select_daily_claim_candidate(sb)

    if candidate is None:
        return None

    candidate_id = candidate.get("id", "")
    locator = (
        "[data-sportzino-daily-claim-id="
        f"'{candidate_id}']"
    )

    print(
        "[Sportzino] Selected Progressive Daily Bonus candidate: "
        f"score={candidate.get('score')} "
        f"context={_short(candidate.get('localText', ''), 180)!r}"
    )

    if _force_click(sb, locator, timeout=4):
        print("[Sportzino] Clicked Progressive Daily Bonus → COLLECT.")
        return candidate

    # Guarded fallback using the currently inspected XPath. It is clicked only
    # when the element still scores as a daily-bonus candidate.
    inspected_xpath = (
        "/html/body/div[1]/div[1]/div/div/div[2]/div[2]/"
        "div[2]/div[1]/div/div[3]/div/div[1]/button"
    )

    for fallback in _daily_claim_candidates(sb):
        if (
            int(fallback.get("score", 0)) >= 800 and
            (
                fallback.get("hasDailyRoot") or
                "DAILY BONUS" in _up(fallback.get("localText", ""))
            )
        ):
            try:
                element = sb.find_element(inspected_xpath)
                element_text = _up(
                    _safe_js(
                        sb,
                        """
                        return arguments[0]
                            ? (
                                arguments[0].innerText ||
                                arguments[0].textContent ||
                                ''
                            )
                            : '';
                        """,
                        element,
                        default="",
                    )
                )

                if element_text == "COLLECT":
                    sb.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        element,
                    )
                    sb.wait(0.3)

                    try:
                        element.click()
                    except Exception:
                        sb.execute_script(
                            "arguments[0].click();",
                            element,
                        )

                    print(
                        "[Sportzino] Clicked guarded inspected XPath for "
                        "Progressive Daily Bonus → COLLECT."
                    )
                    return fallback
            except Exception:
                pass

    print("[Sportzino] The selected daily claim candidate could not be clicked.")
    return None


def _daily_claim_observation(sb: SB) -> Dict[str, Any]:
    """
    Capture the visible state of the Progressive Daily Bonus card and button.
    """
    data = _safe_js(
        sb,
        r"""
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();

            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                style.opacity !== '0' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const normalize = (value) => (value || '')
            .replace(/\s+/g, ' ')
            .trim();

        const dailyRoots = Array.from(document.querySelectorAll(
            '.coin-store-free-rewards-row-item.daily-bonus, ' +
            '[class~="daily-bonus"]'
        )).filter(visible);

        const dailyText = dailyRoots
            .map((root) => normalize(
                root.innerText || root.textContent || ''
            ))
            .join(' | ');

        const collectButtons = dailyRoots.flatMap((root) =>
            Array.from(root.querySelectorAll(
                'button.coin-store-collect-button, ' +
                'button[data-sentry-component="CoinStoreCollectButton"], ' +
                'button'
            )).filter((button) => {
                if (!visible(button)) return false;

                const text = normalize(
                    button.innerText ||
                    button.textContent ||
                    ''
                ).toLowerCase();

                return (
                    text === 'collect' ||
                    text === 'claim' ||
                    text.startsWith('collect ') ||
                    text.startsWith('claim ')
                );
            })
        );

        const enabledCollectButtons = collectButtons.filter(
            (button) => (
                !button.disabled &&
                button.getAttribute('aria-disabled') !== 'true'
            )
        );

        const visibleMessageText = Array.from(document.querySelectorAll(
            '[role="alert"], [role="status"], [role="dialog"], ' +
            '[class*="toast" i], [class*="notification" i], ' +
            '[class*="message" i]'
        )).filter(visible).map((node) =>
            normalize(node.innerText || node.textContent || '')
        ).join(' | ');

        return {
            dailyRootCount: dailyRoots.length,
            dailyText,
            collectCount: collectButtons.length,
            enabledCollectCount: enabledCollectButtons.length,
            visibleMessageText
        };
        """,
        default={},
    )

    if not isinstance(data, dict):
        return {
            "dailyRootCount": 0,
            "dailyText": "",
            "collectCount": 0,
            "enabledCollectCount": 0,
            "visibleMessageText": "",
        }

    return data


def _current_state(sb: SB) -> Dict[str, str]:
    snapshot = _page_snapshot(sb)
    text = snapshot["text"]

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
            "reason": "Visible text reports that the daily bonus is claimed",
            "evidence": claimed_hit,
        }

    success_hit = _first_marker(text, SUCCESS_MARKERS)
    if success_hit:
        return {
            "status": "success",
            "reason": "Visible claim-success text detected",
            "evidence": success_hit,
        }

    if _visible_checkout_detected(sb):
        return {
            "status": "checkout",
            "reason": "A visible checkout/payment dialog was detected",
            "evidence": "VISIBLE CHECKOUT DIALOG",
        }

    if _rewards_dialog_open(sb):
        return {
            "status": "rewards",
            "reason": "Sportzino Coin Store / rewards dialog is open",
            "evidence": "CLAIM FREE REWARDS",
        }

    return {
        "status": "unknown",
        "reason": "Visible page state did not match a known condition",
        "evidence": _short(text, 120),
    }


def _wait_for_claim_result(
    sb: SB,
    before: Dict[str, Any],
    timeout: float = 18,
) -> Dict[str, str]:
    """
    Verify the claim using visible success text or a durable daily-card change.

    A claim is considered verified when:
    - Sportzino shows an explicit success/claimed message; or
    - the previously enabled Daily Bonus Collect button disappears or remains
      disabled for multiple consecutive observations.

    A single transient DOM change is not enough.
    """
    step = 0.5
    loops = max(1, int(timeout / step))
    no_enabled_streak = 0
    retry_used = False
    before_enabled = int(before.get("enabledCollectCount", 0))

    last = {
        "status": "unknown",
        "reason": "No claim-result state yet",
        "evidence": "",
    }

    for index in range(loops):
        state = _current_state(sb)
        observation = _daily_claim_observation(sb)

        combined_visible = " ".join(
            [
                observation.get("dailyText", ""),
                observation.get("visibleMessageText", ""),
            ]
        )

        claimed_hit = _first_marker(
            combined_visible,
            CLAIMED_MARKERS,
        )
        success_hit = _first_marker(
            combined_visible,
            SUCCESS_MARKERS,
        )

        if claimed_hit:
            return {
                "status": "claimed",
                "reason": "Sportzino confirmed the Daily Bonus is claimed",
                "evidence": claimed_hit,
            }

        if success_hit:
            return {
                "status": "success",
                "reason": "Sportzino displayed claim-success text",
                "evidence": success_hit,
            }

        if state["status"] in ("login", "checkout"):
            return state

        enabled_now = int(
            observation.get("enabledCollectCount", 0)
        )

        # The card had an enabled claim before the click. Require the enabled
        # claim control to remain gone/disabled for at least two polls.
        if before_enabled > 0 and enabled_now == 0:
            no_enabled_streak += 1
        else:
            no_enabled_streak = 0

        print(
            "[Sportzino] Claim verification: "
            f"state={state['status']} "
            f"daily_roots={observation.get('dailyRootCount')} "
            f"collect={observation.get('collectCount')} "
            f"enabled_collect={enabled_now} "
            f"gone_streak={no_enabled_streak} "
            f"daily_text={_short(observation.get('dailyText', ''), 160)!r}"
        )

        if no_enabled_streak >= 2:
            return {
                "status": "success",
                "reason": (
                    "The enabled Progressive Daily Bonus Collect button "
                    "disappeared or became disabled after the click"
                ),
                "evidence": (
                    f"before_enabled={before_enabled} "
                    f"after_enabled={enabled_now}"
                ),
            }

        # If the first normal click was swallowed, retry the same high-
        # confidence daily candidate once. Sportzino's claim endpoint should
        # be idempotent, and no unrelated button can pass the score threshold.
        if (
            index == 8 and
            not retry_used and
            enabled_now > 0
        ):
            retry_used = True
            print(
                "[Sportzino] Daily Collect is still enabled; performing one "
                "guarded retry."
            )
            _click_daily_collect(sb)

        last = {
            "status": state["status"],
            "reason": state["reason"],
            "evidence": state["evidence"],
        }

        sb.wait(step)

    return {
        "status": "unverified",
        "reason": (
            "The claim button was clicked, but Sportzino did not provide "
            "a durable success signal"
        ),
        "evidence": last.get("evidence", ""),
    }


# ───────────────────────────────────────────────────────────
# Main UC-based flow
# ───────────────────────────────────────────────────────────

async def Sportzino(ctx, driver, channel: discord.abc.Messageable):
    """
    Sportzino via SeleniumBase UC.

    Discord behavior:
    - The surrounding command/worker may send its normal launch messages.
    - On success, send: Sportzino Daily Bonus Claimed!
    - When unavailable, send: Sportzino Daily Bonus Unavailable.
    - Send the final screenshot after the status message.
    - All other claim details, scoring, and errors are printed locally.

    Claim safety:
    - Scores every visible Collect/Claim control.
    - Requires a strong Progressive Daily Bonus / daily-bonus DOM signal.
    - Rejects Facebook, Google, purchase, checkout, and ambiguous candidates.
    - Verifies success using visible confirmation or a durable button change.
    """
    del ctx, driver

    if ":" not in SPORTZINO_CRED:
        print(
            "[Sportzino][ERROR] SPORTZINO is missing from .env. "
            "Expected email:password."
        )
        return

    username, password = SPORTZINO_CRED.split(":", 1)
    sb: Optional[SB] = None

    try:
        with SB(uc=True, headed=True) as sb:
            # ── Step 1: login ──

            login_result = _login(sb, username, password)
            print(f"[Sportzino] Login result: {login_result}")

            if login_result["status"] != "authenticated":
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Login did not complete — "
                        f"{login_result['reason']}. "
                        "Not attempting a claim."
                    ),
                    "sportzino_login_failed",
                )
                return

            # ── Step 2: normalize to lobby and open Coin Store ──

            current_url = _page_snapshot(sb)["url"]

            if (
                not current_url or
                any(
                    token in current_url.lower()
                    for token in (
                        "/auth/callback",
                        "/connect/authorize",
                        "/login",
                    )
                )
            ):
                sb.open(HOME_URL)

            try:
                sb.wait_for_ready_state_complete()
            except Exception:
                pass

            sb.wait(4)
            _handle_cookie_consent(sb)
            _close_popups_before_rewards(sb)

            if _is_login_page(sb):
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Login session did not persist after "
                        "the lobby redirect."
                    ),
                    "sportzino_session_lost",
                )
                return

            opened_rewards = _open_rewards(sb)

            if not opened_rewards:
                state = _current_state(sb)
                print(
                    "[Sportzino] Could not open Coin Store. "
                    f"Current state: {state}"
                )

                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Coin Store was not found after "
                        "confirmed login."
                    ),
                    "sportzino_rewards_missing",
                )
                return

            sb.wait(4)
            _handle_cookie_consent(sb)

            if not _rewards_dialog_open(sb):
                print(
                    "[Sportzino] Coin Store click occurred, but the visible "
                    "Claim Free Rewards dialog was not confirmed."
                )

            print("[Sportzino] Coin Store / rewards interface opened.")

            # ── Step 3: inspect the Progressive Daily Bonus ──

            pre_state = _current_state(sb)
            before = _daily_claim_observation(sb)

            print(f"[Sportzino] Pre-claim state: {pre_state}")
            print(
                "[Sportzino] Pre-claim daily observation: "
                f"{before}"
            )

            if pre_state["status"] == "login":
                await _send_screenshot(
                    sb,
                    channel,
                    "[Sportzino] Login expired before the claim could run.",
                    "sportzino_login_expired",
                )
                return

            # Checkout is now based only on an actually visible payment dialog.
            if pre_state["status"] == "checkout":
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] A visible checkout/payment dialog was "
                        "detected. No claim button was clicked."
                    ),
                    "sportzino_checkout_pre",
                )
                return

            if pre_state["status"] == "claimed":
                await _send_screenshot(
                    sb,
                    channel,
                    "Sportzino Daily Bonus Unavailable.",
                    "sportzino_already_claimed",
                    discord_message="Sportzino Daily Bonus Unavailable.",
                )
                return

            # ── Step 4: candidate scoring and guarded click ──

            clicked_candidate = _click_daily_collect(sb)

            if clicked_candidate is None:
                after_scan = _daily_claim_observation(sb)

                print(
                    "[Sportzino] No safe Progressive Daily Bonus Collect "
                    "candidate was available."
                )
                print(
                    "[Sportzino] Daily observation after failed scan: "
                    f"{after_scan}"
                )

                await _send_screenshot(
                    sb,
                    channel,
                    "Sportzino Daily Bonus Unavailable.",
                    "sportzino_no_safe_claim",
                    discord_message="Sportzino Daily Bonus Unavailable.",
                )
                return

            # ── Step 5: verify the result ──

            result = _wait_for_claim_result(
                sb,
                before=before,
                timeout=18,
            )

            print(f"[Sportzino] Final claim result: {result}")

            if result["status"] in ("success", "claimed"):
                await _send_screenshot(
                    sb,
                    channel,
                    "Sportzino Daily Bonus Claimed!",
                    "sportzino_claimed",
                    discord_message="Sportzino Daily Bonus Claimed!",
                )
                return

            if result["status"] == "checkout":
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Claim interaction opened a visible "
                        "checkout/payment dialog. Not marking as claimed."
                    ),
                    "sportzino_checkout_false_positive",
                )
                return

            if result["status"] == "login":
                await _send_screenshot(
                    sb,
                    channel,
                    (
                        "[Sportzino] Login expired immediately after the "
                        "claim interaction."
                    ),
                    "sportzino_post_click_login",
                )
                return

            await _send_screenshot(
                sb,
                channel,
                (
                    "[Sportzino] The Progressive Daily Bonus button was "
                    "clicked, but the claim could not be verified."
                ),
                "sportzino_unverified",
            )

    except Exception as error:
        print(f"[Sportzino][ERROR] Exception during automation: {error}")

        try:
            if sb is not None:
                await _send_screenshot(
                    sb,
                    channel,
                    f"[Sportzino][ERROR] Automation crashed: {error}",
                    "sportzino_error",
                )
        except Exception as reporting_error:
            print(
                "[Sportzino][ERROR] Failed while reporting crash: "
                f"{reporting_error}"
            )

