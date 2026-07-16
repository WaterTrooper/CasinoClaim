# Drake Hooks + WaterTrooper
# Casino Claim 3
# Sportzino API (SeleniumBase UC)
# Exact-ID login, non-scrolling cookie handling, and conservative claim verification.

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

def _captcha_looks_ready(sb: SB) -> bool:
    data = _safe_js(
        sb,
        r"""
        const text = (document.body && (document.body.innerText || document.body.textContent) || '')
            .replace(/\s+/g, ' ')
            .toLowerCase();

        const response = document.querySelector(
            'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"], ' +
            'input[name="g-recaptcha-response"], textarea[name="g-recaptcha-response"]'
        );
        const token = response ? (response.value || '') : '';

        const form = document.querySelector('form.login-form') ||
            document.querySelector('#emailAddress')?.closest('form');
        const button = form && form.querySelector(
            '.login-form-login-button-container button, button[type="submit"], button[data-testid="login-submit-button"]'
        );
        const enabled = Boolean(button && !button.disabled && button.getAttribute('aria-disabled') !== 'true');

        return {
            successText: text.includes('success!') ||
                text.includes('verification successful') ||
                text.includes('challenge passed'),
            tokenReady: token.length > 10,
            submitEnabled: enabled,
            hasChallenge: Boolean(document.querySelector(
                'iframe[src*="challenges.cloudflare.com"], .cf-turnstile, [data-sitekey]'
            ))
        };
        """,
        default={},
    )

    if not isinstance(data, dict):
        return False

    return bool(
        data.get("successText")
        or data.get("tokenReady")
        or (data.get("submitEnabled") and not data.get("hasChallenge"))
    )


def _login_values_present(sb: SB, username: str, password: str) -> bool:
    values = _safe_js(
        sb,
        """
        const email = document.querySelector('#emailAddress, input[data-testid="login-email-input"]');
        const password = document.querySelector('#password, input[data-testid="login-password-input"]');
        return {
            email: email ? (email.value || '') : '',
            password: password ? (password.value || '') : ''
        };
        """,
        default={},
    )
    return isinstance(values, dict) and values.get("email") == username and values.get("password") == password


def _focus_login_form(sb: SB) -> None:
    """Return to the login form after any GUI captcha interaction."""
    _safe_js(
        sb,
        """
        const email = document.querySelector('#emailAddress, input[data-testid="login-email-input"]');
        if (email) {
            email.scrollIntoView({block: 'center', inline: 'nearest'});
        } else {
            window.scrollTo({top: 0, left: 0, behavior: 'instant'});
        }
        """,
        default=None,
    )


def _submit_login(sb: SB, password_locator: str) -> bool:
    # First use the exact form-scoped button. No scroll_to() is used here.
    for locator in SUBMIT_LOCATORS:
        try:
            sb.wait_for_element_visible(locator, timeout=2)
            button = sb.find_element(locator)
            disabled = _safe_js(
                sb,
                "return Boolean(arguments[0].disabled || arguments[0].getAttribute('aria-disabled') === 'true');",
                button,
                default=True,
            )
            if disabled:
                continue

            sb.execute_script("arguments[0].click();", button)
            print(f"[Sportzino] Login submitted with: {locator}")
            return True
        except Exception:
            continue

    # DOM fallback stays scoped to the form containing #emailAddress.
    submitted = bool(
        _safe_js(
            sb,
            """
            const email = document.querySelector('#emailAddress, input[data-testid="login-email-input"]');
            const form = email && email.closest('form');
            if (!form) return false;

            const button = form.querySelector(
                '.login-form-login-button-container button, button[type="submit"], button[data-testid="login-submit-button"]'
            );
            if (button && !button.disabled && button.getAttribute('aria-disabled') !== 'true') {
                button.click();
                return true;
            }

            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
                return true;
            }
            return false;
            """,
            default=False,
        )
    )
    if submitted:
        print("[Sportzino] Login submitted through the containing form.")
        return True

    try:
        sb.press_keys(password_locator, "\n")
        print("[Sportzino] Login submitted with Enter fallback.")
        return True
    except Exception:
        return False


def _wait_for_authentication(
    sb: SB,
    password_locator: str,
    timeout: float = 45,
) -> Dict[str, str]:
    """Wait for the login controls to disappear and the URL to leave /login."""
    step = 1.0
    loops = max(1, int(timeout / step))
    last = {"status": "unknown", "reason": "No state yet", "evidence": ""}

    for index in range(loops):
        # Cookie handling is deliberately infrequent and overlay-only. The old
        # code clicked the static footer's Manage Cookies link every second,
        # which is exactly what dragged the browser to the bottom of the page.
        if index in (0, 10, 25):
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
                "reason": "Login controls disappeared and the browser left the login route",
                "evidence": snapshot["url"],
            }

        last = {
            "status": "login_pending",
            "reason": "Still on the login page after submitting the form",
            "evidence": snapshot["url"],
        }

        # Retry the same form submission after a delayed Turnstile completion.
        if index in (8, 18, 30) and _captcha_looks_ready(sb):
            _focus_login_form(sb)
            _submit_login(sb, password_locator)

        sb.wait(step)

    return last


def _login(sb: SB, username: str, password: str) -> Dict[str, str]:
    sb.uc_open_with_reconnect(LOGIN_URL, 4)
    sb.wait_for_ready_state_complete()
    print("[Sportzino] Login page loaded.")

    try:
        sb.wait_for_element_visible("#emailAddress", timeout=20)
        sb.wait_for_element_visible("#password", timeout=20)
    except Exception:
        # Continue through fallback locators so a small markup change still has
        # a chance to work and produces a useful result message.
        pass

    # Start at the form, not the footer. Cookie handling below cannot scroll.
    _safe_js(sb, "window.scrollTo({top: 0, left: 0, behavior: 'instant'});", default=None)
    _handle_cookie_consent(sb)

    email_locator = _fill_input(sb, EMAIL_LOCATORS, username, "email")
    password_locator = _fill_input(sb, PASSWORD_LOCATORS, password, "password")

    if not email_locator or not password_locator:
        return {
            "status": "login_fields_missing",
            "reason": "The current #emailAddress/#password inputs could not be filled",
            "evidence": f"email={bool(email_locator)} password={bool(password_locator)}",
        }

    if not _login_values_present(sb, username, password):
        return {
            "status": "login_fields_rejected",
            "reason": "Sportzino cleared or rejected one of the login field values",
            "evidence": "The values did not remain in #emailAddress and #password",
        }

    sb.wait(1.0)

    # Only invoke SeleniumBase's GUI captcha helper when the page has not
    # already reached the visible Success state shown in the supplied image.
    if not _captcha_looks_ready(sb):
        try:
            sb.uc_gui_click_captcha()
            print("[Sportzino] Cloudflare captcha click attempted.")
        except Exception as exc:
            print(f"[Sportzino] Captcha click was unnecessary or unavailable: {exc}")

    for _ in range(30):
        if _captcha_looks_ready(sb):
            break
        sb.wait(0.5)

    # GUI captcha interaction can move the viewport. Put the actual login form
    # back in view, then verify/refill the exact IDs before submitting.
    _focus_login_form(sb)
    _handle_cookie_consent(sb)

    if not _login_values_present(sb, username, password):
        email_locator = _fill_input(sb, EMAIL_LOCATORS, username, "email")
        password_locator = _fill_input(sb, PASSWORD_LOCATORS, password, "password")

    if not email_locator or not password_locator or not _login_values_present(sb, username, password):
        return {
            "status": "login_fields_lost",
            "reason": "The login values disappeared before form submission",
            "evidence": "Could not restore #emailAddress/#password",
        }

    if not _submit_login(sb, password_locator):
        return {
            "status": "submit_failed",
            "reason": "Could not click or submit the Sportzino login form",
            "evidence": "No enabled form-scoped Log In button was available",
        }

    return _wait_for_authentication(sb, password_locator, timeout=45)


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
    - Uses the exact #emailAddress and #password IDs first.
    - Never clicks the static footer Manage Cookies link or scrolls there.
    - Accepts or neutralizes only a real fixed/sticky cookie overlay.
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
