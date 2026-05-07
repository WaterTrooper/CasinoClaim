# Drake Hooks
# Casino Claim 3
# Luck Party API (SeleniumBase UC)

import os
import time
import contextlib
from pathlib import Path
from typing import Optional, Tuple, List

import discord
from dotenv import load_dotenv
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


load_dotenv()

SITE_NAME = "Luck Party"
LOGIN_URL = "https://luckparty.com/login"
LOBBY_URL = "https://luckparty.com/lobby"

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


# ───────────────────────────────────────────────────────────
# ENV
# ───────────────────────────────────────────────────────────

def first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def get_luckparty_credentials() -> Tuple[str, str]:
    """
    Supports:
      LUCKPARTY_LOGIN=email:password

    Also accepts:
      LUCKPARTY_EMAIL=email
      LUCKPARTY_PASSWORD=password

    And LUCKYPARTY_* variants for compatibility.
    """
    combined = first_env(
        "LUCKPARTY_LOGIN",
        "LUCK_PARTY_LOGIN",
        "LUCKYPARTY_LOGIN",
        "LUCKY_PARTY_LOGIN",
    )

    if combined and ":" in combined:
        email, password = combined.split(":", 1)
        return email.strip(), password.strip()

    email = first_env(
        "LUCKPARTY_EMAIL",
        "LUCK_PARTY_EMAIL",
        "LUCKYPARTY_EMAIL",
        "LUCKY_PARTY_EMAIL",
        "LUCKPARTYEMAIL",
        "LUCKYPARTYEMAIL",
    )

    password = first_env(
        "LUCKPARTY_PASSWORD",
        "LUCK_PARTY_PASSWORD",
        "LUCKYPARTY_PASSWORD",
        "LUCKY_PARTY_PASSWORD",
        "LUCKPARTYPASSWORD",
        "LUCKYPARTYPASSWORD",
    )

    return email, password


# ───────────────────────────────────────────────────────────
# DISCORD
# ───────────────────────────────────────────────────────────

async def send_screenshot(sb: SB, channel: discord.abc.Messageable, filename: str, caption: str):
    path = str(SCREENSHOT_DIR / filename)

    try:
        sb.save_screenshot(path)
        await channel.send(caption, file=discord.File(path))
    finally:
        with contextlib.suppress(Exception):
            if os.path.exists(path):
                os.remove(path)


# ───────────────────────────────────────────────────────────
# BASIC HELPERS
# ───────────────────────────────────────────────────────────

def sleep(seconds: float):
    time.sleep(seconds)


def current_url(sb: SB) -> str:
    try:
        return sb.get_current_url()
    except Exception:
        with contextlib.suppress(Exception):
            return sb.driver.current_url
    return ""


def body_text(sb: SB) -> str:
    try:
        return sb.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        return ""


def wait_ready(sb: SB):
    with contextlib.suppress(Exception):
        sb.wait_for_ready_state_complete()


def wait_until(fn, timeout: int = 30, poll: float = 0.5) -> bool:
    end = time.time() + timeout

    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass

        sleep(poll)

    return False


def open_url(sb: SB, url: str, expected_domain: str) -> bool:
    with contextlib.suppress(Exception):
        sb.driver.set_window_size(1428, 940)

    try:
        sb.uc_open_with_reconnect(url, 4)
    except Exception:
        try:
            sb.open(url)
        except Exception:
            return False

    wait_ready(sb)
    sleep(3)

    return expected_domain in current_url(sb).lower()


def element_exists(sb: SB, selector: str) -> bool:
    try:
        return bool(sb.execute_script("return !!document.querySelector(arguments[0]);", selector))
    except Exception:
        return False


# ───────────────────────────────────────────────────────────
# CLICK / INPUT HELPERS
# ───────────────────────────────────────────────────────────

CLICK_ELEMENT_JS = """
const el = arguments[0];
if (!el) return false;

el.scrollIntoView({ block: "center", inline: "center" });

["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(type => {
    el.dispatchEvent(new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        view: window
    }));
});

try { el.click(); } catch (e) {}

return true;
"""


def click_selectors(sb: SB, selectors: List[str], timeout: int = 8) -> bool:
    script = """
    const selectors = arguments[0];

    function visible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            style.opacity !== "0" &&
            rect.width > 0 &&
            rect.height > 0
        );
    }

    function clickLikeHuman(el) {
        el.scrollIntoView({ block: "center", inline: "center" });

        ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(type => {
            el.dispatchEvent(new MouseEvent(type, {
                bubbles: true,
                cancelable: true,
                view: window
            }));
        });

        try { el.click(); } catch (e) {}
        return true;
    }

    for (const selector of selectors) {
        const els = Array.from(document.querySelectorAll(selector))
            .filter(el => visible(el) && !el.disabled);

        if (els.length) {
            return clickLikeHuman(els[0]);
        }
    }

    return false;
    """

    return wait_until(lambda: bool(sb.execute_script(script, selectors)), timeout=timeout)


def click_xpaths(sb: SB, xpaths: List[str], timeout: int = 8) -> bool:
    end = time.time() + timeout

    while time.time() < end:
        for xpath in xpaths:
            try:
                els = sb.driver.find_elements(By.XPATH, xpath)
                els = [el for el in els if el.is_displayed() and el.is_enabled()]

                if els:
                    sb.execute_script(CLICK_ELEMENT_JS, els[0])
                    return True
            except Exception:
                continue

        sleep(0.4)

    return False


def click_by_text(
    sb: SB,
    text_options: List[str],
    selectors: str = "button, [role='button'], a, div, span",
    timeout: int = 8,
) -> bool:
    script = """
    const wanted = arguments[0].map(t => String(t).trim().toUpperCase());
    const selectors = arguments[1];

    function visible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            style.opacity !== "0" &&
            rect.width > 0 &&
            rect.height > 0
        );
    }

    function score(el) {
        let s = 0;
        const tag = el.tagName || "";
        const cls = String(el.className || "").toLowerCase();

        if (tag === "BUTTON") s += 40;
        if (cls.includes("btn")) s += 10;
        if (cls.includes("button")) s += 10;
        if (cls.includes("submit")) s += 10;
        if (cls.includes("active")) s += 5;
        if (cls.includes("collect")) s += 5;
        if (cls.includes("get-coins")) s += 5;

        return s;
    }

    function clickLikeHuman(el) {
        el.scrollIntoView({ block: "center", inline: "center" });

        ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(type => {
            el.dispatchEvent(new MouseEvent(type, {
                bubbles: true,
                cancelable: true,
                view: window
            }));
        });

        try { el.click(); } catch (e) {}
        return true;
    }

    const matches = Array.from(document.querySelectorAll(selectors))
        .filter(el => {
            if (!visible(el) || el.disabled) return false;

            const text = (el.innerText || el.textContent || "")
                .replace(/\\s+/g, " ")
                .trim()
                .toUpperCase();

            return text && wanted.some(w => text.includes(w));
        })
        .sort((a, b) => score(b) - score(a));

    if (!matches.length) return false;

    return clickLikeHuman(matches[0]);
    """

    return wait_until(lambda: bool(sb.execute_script(script, text_options, selectors)), timeout=timeout)


def set_react_input_any(sb: SB, selectors: List[str], value: str, timeout: int = 12) -> bool:
    script = """
    const selectors = arguments[0];
    const value = arguments[1];

    function visible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0
        );
    }

    for (const selector of selectors) {
        const inputs = Array.from(document.querySelectorAll(selector)).filter(visible);

        if (!inputs.length) continue;

        const input = inputs[0];
        input.scrollIntoView({ block: "center", inline: "center" });
        input.focus();

        const nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype,
            "value"
        ).set;

        nativeSetter.call(input, value);

        input.dispatchEvent(new InputEvent("input", {
            bubbles: true,
            inputType: "insertText",
            data: value
        }));

        input.dispatchEvent(new Event("change", { bubbles: true }));

        return input.value === value;
    }

    return false;
    """

    if wait_until(lambda: bool(sb.execute_script(script, selectors, value)), timeout=timeout):
        sleep(0.4)
        return True

    for selector in selectors:
        with contextlib.suppress(Exception):
            sb.wait_for_element_visible(selector, timeout=2)
            sb.clear(selector)
            sb.type(selector, value)
            sleep(0.4)
            return True

    return False


def press_enter_on_any(sb: SB, selectors: List[str]) -> bool:
    for selector in selectors:
        with contextlib.suppress(Exception):
            el = sb.driver.find_element(By.CSS_SELECTOR, selector)
            if el.is_displayed() and el.is_enabled():
                el.send_keys(Keys.ENTER)
                return True

    return False


# ───────────────────────────────────────────────────────────
# PAGE STATE
# ───────────────────────────────────────────────────────────

def is_logged_in(sb: SB) -> bool:
    url = current_url(sb).lower()
    text = body_text(sb).lower()

    return (
        "/lobby" in url
        or element_exists(sb, "button.get-coins-btn")
        or ("get coins" in text and ("continue playing" in text or "lobby" in text))
    )


def wait_for_logged_in(sb: SB, timeout: int = 45) -> bool:
    def _check():
        text = body_text(sb).lower()

        if "invalid" in text or "incorrect" in text or "wrong password" in text:
            return False

        return is_logged_in(sb)

    return wait_until(_check, timeout=timeout, poll=1)


def wait_for_coin_store(sb: SB, timeout: int = 25) -> bool:
    def _check():
        text = body_text(sb).upper()

        if "CLAIM FREE REWARDS" in text:
            return True

        if "DAILY BONUS" in text and "COLLECT" in text:
            return True

        return bool(
            sb.execute_script(
                """
                return !!(
                    document.querySelector(".free-coins-dialog") ||
                    document.querySelector(".free-reward") ||
                    document.querySelector("[data-sentry-component='FreeReward']")
                );
                """
            )
        )

    return wait_until(_check, timeout=timeout)


# ───────────────────────────────────────────────────────────
# LOGIN
# ───────────────────────────────────────────────────────────

EMAIL_SELECTORS = [
    "#field-email",
    "input#field-email",
    "input[name='email']",
    "input[type='email']",
    "input[placeholder='Email']",
    "input[autocomplete='email']",
]

PASSWORD_SELECTORS = [
    "#field-password",
    "input#field-password",
    "input[name='password']",
    "input[type='password']",
    "input[placeholder='Password']",
    "input[autocomplete='current-password']",
]


def login_luckparty(sb: SB) -> str:
    if not open_url(sb, LOGIN_URL, "luckparty.com"):
        return "open_failed"

    if is_logged_in(sb):
        return "ok"

    email, password = get_luckparty_credentials()

    if not set_react_input_any(sb, EMAIL_SELECTORS, email):
        return "login_failed"

    if not set_react_input_any(sb, PASSWORD_SELECTORS, password):
        return "login_failed"

    with contextlib.suppress(Exception):
        sb.uc_gui_click_captcha()
        sb.wait(10)

    if press_enter_on_any(sb, PASSWORD_SELECTORS):
        sleep(6)
        wait_ready(sb)
        if wait_for_logged_in(sb, timeout=25):
            return "ok"

    if click_selectors(sb, ["form button[type='submit']"], timeout=5):
        sleep(6)
        wait_ready(sb)
        return "ok" if wait_for_logged_in(sb, timeout=30) else "login_failed"

    if click_by_text(sb, ["LOG IN", "LOGIN", "SIGN IN"], selectors="button, [role='button']", timeout=5):
        sleep(6)
        wait_ready(sb)
        return "ok" if wait_for_logged_in(sb, timeout=30) else "login_failed"

    if click_xpaths(
        sb,
        [
            "//form//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'LOG IN')]",
            "//form//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'LOGIN')]",
            "//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'LOG IN')]",
            "//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'LOGIN')]",
        ],
        timeout=5,
    ):
        sleep(6)
        wait_ready(sb)
        return "ok" if wait_for_logged_in(sb, timeout=30) else "login_failed"

    return "login_failed"


# ───────────────────────────────────────────────────────────
# CLAIM FLOW
# ───────────────────────────────────────────────────────────

def close_popups(sb: SB):
    click_xpaths(
        sb,
        [
            "//button[contains(@class, 'close')]",
            "//button[contains(@aria-label, 'close')]",
            "//button[contains(@aria-label, 'Close')]",
            "//button[contains(text(), '×')]",
            "//button[contains(., 'Accept All')]",
            "//button[contains(., 'ACCEPT ALL')]",
            "/html/body/div[5]/div/div[1]/div/div/button",
            "/html/body/div[4]/div/div[1]/div/div/button",
            "/html/body/div[6]/div/div[1]/div/div/button",
        ],
        timeout=2,
    )

    with contextlib.suppress(Exception):
        sb.press_keys("body", "\ue00c")
        sleep(0.5)


def open_lobby_if_needed(sb: SB):
    if "/lobby" in current_url(sb).lower():
        return

    open_url(sb, LOBBY_URL, "luckparty.com")


def open_coin_store(sb: SB) -> bool:
    open_lobby_if_needed(sb)
    close_popups(sb)
    sleep(1)

    if click_selectors(
        sb,
        [
            "button.get-coins-btn",
            "button[data-sentry-component='GetCoinsButton']",
            "button[class*='get-coins']",
        ],
        timeout=6,
    ):
        sleep(2)
        return wait_for_coin_store(sb, timeout=20)

    if click_by_text(
        sb,
        ["GET COINS", "COIN STORE", "STORE", "REWARDS", "BUY COINS"],
        selectors="button, [role='button'], a, div",
        timeout=6,
    ):
        sleep(2)
        return wait_for_coin_store(sb, timeout=20)

    return False


def click_collect_reward(sb, prefer_daily: bool = True) -> bool:
    script = """
    const preferDaily = arguments[0];

    function clean(s) {
        return String(s || "").replace(/\\s+/g, " ").trim();
    }

    function visible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            style.opacity !== "0" &&
            rect.width > 0 &&
            rect.height > 0
        );
    }

    const candidates = [];

    const cards = Array.from(document.querySelectorAll(
        ".free-reward, [data-sentry-component='FreeReward']"
    )).filter(visible);

    for (const card of cards) {
        const titleEl =
            card.querySelector(".free-reward__title") ||
            card.querySelector("[class*='title']");

        const title = clean(titleEl ? titleEl.innerText : card.innerText);

        const buttons = Array.from(card.querySelectorAll("button"))
            .filter(button => {
                const txt = clean(button.innerText).toUpperCase();
                const cls = String(button.className || "").toLowerCase();

                return (
                    visible(button) &&
                    !button.disabled &&
                    (
                        txt.includes("COLLECT") ||
                        cls.includes("collect")
                    )
                );
            });

        for (const button of buttons) {
            candidates.push({ title, button });
        }
    }

    if (!candidates.length) {
        const buttons = Array.from(document.querySelectorAll(
            "button.free-reward__button.collect, button[class*='collect'], button"
        )).filter(button => {
            const txt = clean(button.innerText).toUpperCase();
            const cls = String(button.className || "").toLowerCase();

            return (
                visible(button) &&
                !button.disabled &&
                (
                    txt.includes("COLLECT") ||
                    cls.includes("collect")
                )
            );
        });

        for (const button of buttons) {
            const card =
                button.closest(".free-reward") ||
                button.closest("[data-sentry-component='FreeReward']") ||
                button.parentElement;

            candidates.push({
                title: clean(card ? card.innerText : button.innerText),
                button
            });
        }
    }

    if (!candidates.length) return false;

    let chosen = candidates[0];

    if (preferDaily) {
        const daily = candidates.find(item =>
            clean(item.title).toUpperCase().includes("DAILY BONUS")
        );

        if (daily) chosen = daily;
    }

    chosen.button.scrollIntoView({ block: "center", inline: "center" });

    ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(type => {
        chosen.button.dispatchEvent(new MouseEvent(type, {
            bubbles: true,
            cancelable: true,
            view: window
        }));
    });

    try { chosen.button.click(); } catch (e) {}

    return true;
    """

    try:
        if sb.execute_script(script, bool(prefer_daily)):
            sleep(3)
            return True
    except Exception:
        pass

    if click_xpaths(
        sb,
        [
            "/html/body/div[5]/div/div[2]/div/div[2]/div[2]/div[1]/div[4]/button[1]",
            "//button[contains(@class, 'free-reward__button') and contains(@class, 'collect')]",
            "//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'COLLECT')]",
        ],
        timeout=4,
    ):
        sleep(3)
        return True

    return False


def collect_available_rewards(sb: SB, max_clicks: int = 2) -> bool:
    claimed_any = False

    for i in range(max_clicks):
        if not click_collect_reward(sb, prefer_daily=(i == 0)):
            break

        claimed_any = True

    return claimed_any


def run_claim_flow(sb: SB) -> str:
    login_result = login_luckparty(sb)

    if login_result != "ok":
        return login_result

    wait_ready(sb)
    sleep(2)

    close_popups(sb)

    if not open_coin_store(sb):
        return "store_failed"

    sleep(2)

    return "claimed" if collect_available_rewards(sb, max_clicks=2) else "unavailable"


# ───────────────────────────────────────────────────────────
# PUBLIC RUNNERS
# ───────────────────────────────────────────────────────────

async def luckparty_casino(ctx=None, driver=None, channel: Optional[discord.abc.Messageable] = None):
    if channel is None and ctx is not None:
        channel = ctx.channel

    if channel is None:
        raise RuntimeError("luckparty_casino needs a Discord channel or ctx.")

    email, password = get_luckparty_credentials()

    if not email or not password:
        await channel.send(
            "❌ Missing Luck Party credentials in `.env`.\n\n"
            "Supported formats:\n"
            "`LUCKPARTY_LOGIN=email:password`\n\n"
            "or:\n"
            "`LUCKPARTY_EMAIL=email`\n"
            "`LUCKPARTY_PASSWORD=password`"
        )
        return

    await channel.send("Launching **Luck Party** (UC)...")

    try:
        with SB(uc=True, headed=True) as sb:
            try:
                result = run_claim_flow(sb)

                captions = {
                    "claimed": "Luck Party Daily Bonus Claimed!",
                    "unavailable": "[Luck Party] Bonus unavailable (likely already claimed).",
                    "open_failed": "[Luck Party] Could not open the login page.",
                    "login_failed": "[Luck Party] Login failed.",
                    "store_failed": "[Luck Party] Could not open the coin store or rewards modal.",
                }

                filename = f"luckparty_{result}.png"
                caption = captions.get(result, f"[Luck Party] Unknown result: {result}")

                await send_screenshot(sb, channel, filename, caption)

            except Exception as e:
                await send_screenshot(
                    sb,
                    channel,
                    "luckparty_error.png",
                    f"[Luck Party] Claim error: {type(e).__name__}: {e}",
                )

    except Exception as e:
        await channel.send(f"[Luck Party] Browser error: `{type(e).__name__}: {e}`")


async def luckparty_uc(ctx=None, channel: Optional[discord.abc.Messageable] = None):
    await luckparty_casino(ctx=ctx, channel=channel)


async def claim_luckparty(
    channel: Optional[discord.abc.Messageable] = None,
    ctx=None,
    driver=None,
    headless=None,
):
    await luckparty_casino(ctx=ctx, driver=driver, channel=channel)


async def claim_bonus(channel=None, headless=None):
    await claim_luckparty(channel=channel)


async def run(channel=None, headless=None):
    await claim_luckparty(channel=channel)


async def main(channel=None, headless=None):
    await claim_luckparty(channel=channel)


# Backward-compatible aliases.
async def claim_luckyparty(
    channel: Optional[discord.abc.Messageable] = None,
    ctx=None,
    driver=None,
    headless=None,
):
    await claim_luckparty(channel=channel, ctx=ctx, driver=driver, headless=headless)


async def luckyparty_casino(ctx=None, driver=None, channel: Optional[discord.abc.Messageable] = None):
    await luckparty_casino(ctx=ctx, driver=driver, channel=channel)


async def luckyparty_uc(ctx=None, channel: Optional[discord.abc.Messageable] = None):
    await luckparty_uc(ctx=ctx, channel=channel)


if __name__ == "__main__":
    with SB(uc=True, headed=True) as sb:
        opened = open_url(sb, LOGIN_URL, "luckparty.com")
        print("Opened:", opened, current_url(sb))
        sleep(10)