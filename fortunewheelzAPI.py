# Drake Hooks + WaterTrooper
# Casino Claim 3
# Fortune Wheelz API
# Version 3.5
# Updated 2026.05.12
#
# Notes:
# - Keeps the working Fortune Wheelz claim flow.
# - Fixes false-positive claims when the promo card says "Next in HH:MM:SS".
# - Reads countdown before trying to click the daily reward card.
# - Uses the new countdown XPath fallback:
#   /html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[4]/div/div[1]/div[2]/button
# - Keeps backwards compatibility with main.py by exposing both:
#   fortunewheelz_casino()
#   fortunewheelz_flow()

import re
import os
import asyncio
import discord
from dotenv import load_dotenv

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# ───────────────────────────────────────────────────────────
# Config & Constants
# ───────────────────────────────────────────────────────────

load_dotenv()

FORTUNEWHEELZ_CRED = os.getenv("FORTUNEWHEELZ")  # format "email:password"

SITE_URL = "https://fortunewheelz.com"
LOGIN_URL = "https://fortunewheelz.com/signin"
LOBBY_URL = "https://fortunewheelz.com/lobby"
PROMOTIONS_URL = "https://fortunewheelz.com/promotions"

LOGIN_BUTTON_XPATH = "//button[@data-tid='header-login-btn']"
EMAIL_INPUT_XPATH = "//input[@data-tid='login-email-input']"
PASSWORD_INPUT_XPATH = "//input[@data-tid='login-password-input']"
LOGIN_SUBMIT_XPATH = "//button[@data-tid='login-btn']"

# Daily reward promo-card button.
# Important: this same selector can be either available OR "Next in HH:MM:SS".
CLAIM_REWARD_XPATH = "//button[@data-tid='promo-daily-login-button']"

# Final claim button inside the daily reward modal.
CLAIM_BUTTON_XPATH = "//button[@data-tid='daily-login-btn']"

# Exact daily reward countdown buttons.
# New one from your screenshot is first.
DAILY_CARD_COUNTDOWN_XPATHS = [
    "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[4]/div/div[1]/div[2]/button",
    "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[3]/div/div[1]/div[2]/button",
]

# Modal countdown fallbacks after opening the reward card.
MODAL_COUNTDOWN_XPATHS = [
    "/html/body/div[3]/div/div[2]/div[3]/p",
    "/html/body/div[4]/div/div[2]/div[3]/p",
    "/html/body/div[5]/div/div[2]/div[3]/p",
    "/html/body/div[6]/div/div[2]/div[3]/p",
    "/html/body/div[7]/div/div[2]/div[3]/p",
    "/html/body/div[8]/div/div[2]/div[3]/p",
    "/html/body/div[9]/div/div[2]/div[3]/p",
]

# Generic but still scoped to the daily login promo button.
COUNTDOWN_LOCATORS = [
    # Your exact daily card paths.
    *[(By.XPATH, xp) for xp in DAILY_CARD_COUNTDOWN_XPATHS],

    # Any Daily Reward promo button saying Next in / containing HH:MM:SS.
    (
        By.XPATH,
        "//button[@data-tid='promo-daily-login-button' "
        "and (contains(normalize-space(.), 'Next in') or contains(normalize-space(.), ':'))]"
    ),

    # CSS class says disabled and text has countdown.
    (
        By.XPATH,
        "//button[@data-tid='promo-daily-login-button' "
        "and contains(@class, 'disabled') "
        "and contains(normalize-space(.), ':')]"
    ),

    # Modal paragraph fallback.
    *[(By.XPATH, xp) for xp in MODAL_COUNTDOWN_XPATHS],

    # Final fallback: any disabled-ish button that says Next in.
    (
        By.XPATH,
        "//button[contains(@class, 'disabled') "
        "and contains(normalize-space(.), 'Next in') "
        "and contains(normalize-space(.), ':')]"
    ),
]

POPUP_CLOSE_XPATHS = [
    "/html/body/div[3]/div/div[1]/span",
    "/html/body/div[4]/div/div[1]/span",
    "/html/body/div[5]/div/div[1]/span",
    "/html/body/div[6]/div/div[1]/span",
    "/html/body/div[7]/div/div[1]/span",
    "/html/body/div[8]/div/div[1]/span",
    "/html/body/div[9]/div/div[1]/span",
]


# ───────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//div[@class='balance-switcher']")
        return True
    except NoSuchElementException:
        pass

    try:
        driver.find_element(By.XPATH, "//button[@data-tid='header-buy-btn']")
        return True
    except NoSuchElementException:
        return False


def _wait_clickable(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _wait_present(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _safe_click(driver, element, label="element") -> bool:
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            element
        )
        asyncio.sleep(0)
    except Exception:
        pass

    try:
        element.click()
        print(f"[Fortune Wheelz] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[Fortune Wheelz] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[Fortune Wheelz] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[Fortune Wheelz] JS click failed for {label}: {e}")

    return False


def _normalize_countdown(text: str) -> str | None:
    """
    Accepts:
      - Next in 02:45:59
      - 02:45:59
      - 2 : 45 : 59

    Returns:
      - HH:MM:SS
      - None
    """
    if not text:
        return None

    match = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*:\s*(\d{2})", text)

    if not match:
        return None

    hours, minutes, seconds = match.groups()
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def _element_text(driver, element) -> str:
    """
    Selenium .text sometimes misses Vue button text.
    This falls back to JS innerText/textContent.
    """
    texts = []

    try:
        texts.append(element.text or "")
    except Exception:
        pass

    try:
        texts.append(driver.execute_script("return arguments[0].innerText || '';", element) or "")
    except Exception:
        pass

    try:
        texts.append(driver.execute_script("return arguments[0].textContent || '';", element) or "")
    except Exception:
        pass

    return " ".join(t.strip() for t in texts if t and t.strip()).strip()


def _button_looks_disabled(driver, element) -> bool:
    """
    Fortune Wheelz uses CSS class 'disabled' instead of always using real disabled attr.
    Selenium may still think the button is clickable, so check manually.
    """
    try:
        classes = (element.get_attribute("class") or "").lower()
        if "disabled" in classes:
            return True
    except Exception:
        pass

    for attr in ("disabled", "aria-disabled"):
        try:
            value = (element.get_attribute(attr) or "").strip().lower()
            if value in {"true", "disabled", "1"}:
                return True
        except Exception:
            pass

    text = _element_text(driver, element).lower()

    if "next in" in text:
        return True

    if _normalize_countdown(text):
        return True

    return False


def _read_countdown(driver) -> str | None:
    """
    Reads countdown from the daily reward card first, then modal fallbacks.
    Avoids generic page-wide countdowns so it does not accidentally grab
    tournament or promo timers.
    """
    for by, value in COUNTDOWN_LOCATORS:
        try:
            elements = driver.find_elements(by, value)

            for element in elements:
                try:
                    text = _element_text(driver, element)
                    countdown = _normalize_countdown(text)

                    if countdown:
                        print(f"[Fortune Wheelz] Countdown found: {countdown} from text: {text!r}")
                        return countdown

                except Exception:
                    continue

        except Exception:
            continue

    return None


def _find_daily_reward_button(driver):
    """
    Finds the Fortune Wheelz daily login promo button.
    This can be either:
      - Available claim button
      - Disabled-looking countdown button: Next in HH:MM:SS
    """
    try:
        buttons = driver.find_elements(By.XPATH, CLAIM_REWARD_XPATH)
    except Exception:
        return None

    if not buttons:
        return None

    # Prefer the first visible daily reward promo button.
    for btn in buttons:
        try:
            if btn.is_displayed():
                return btn
        except Exception:
            continue

    return buttons[0]


def _close_popups(driver, max_passes=2):
    """
    Tries to close annoying Fortune Wheelz popups without breaking the page.
    """
    def try_click(el):
        try:
            el.click()
            return True
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False

    for _ in range(max_passes):
        closed_any = False

        for xp in POPUP_CLOSE_XPATHS:
            try:
                close_btn = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )

                if try_click(close_btn):
                    print(f"[Fortune Wheelz] Closed popup with XPath: {xp}")
                    closed_any = True

            except Exception:
                pass

        try:
            close_elements = driver.find_elements(
                By.CSS_SELECTOR,
                "span.close, span[data-tid*='close'], button[data-tid*='close']"
            )

            for el in close_elements:
                if try_click(el):
                    print("[Fortune Wheelz] Closed popup with generic close selector.")
                    closed_any = True

        except Exception:
            pass

        try:
            spans = driver.find_elements(By.TAG_NAME, "span")

            for el in spans:
                try:
                    text = (el.text or "").strip().lower()

                    if text in ("x", "×", "close"):
                        if try_click(el):
                            print("[Fortune Wheelz] Closed popup with visible X/close span.")
                            closed_any = True

                except Exception:
                    continue

        except Exception:
            pass

        if not closed_any:
            break


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[Fortune Wheelz] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


async def _send_countdown_or_unavailable(channel, driver):
    countdown = _read_countdown(driver)

    if countdown:
        await _send_screenshot(
            channel,
            driver,
            f"Next Fortune Wheelz Bonus Available in: {countdown}",
            "fortunewheelz_countdown.png"
        )
        return True

    await _send_screenshot(
        channel,
        driver,
        "Fortune Wheelz Daily Bonus Unavailable.",
        "fortunewheelz_claim_error.png"
    )
    return False


# ───────────────────────────────────────────────────────────
# Login Flow
# ───────────────────────────────────────────────────────────

async def fortunewheelz_casino(ctx, driver, channel):
    if not FORTUNEWHEELZ_CRED:
        await channel.send("❌ Missing `FORTUNEWHEELZ` as 'email:password' in your .env.")
        return

    username, password = FORTUNEWHEELZ_CRED.split(":", 1)

    print("[Fortune Wheelz] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)

    if _is_logged_in(driver):
        print("[Fortune Wheelz] Already logged in.")
        await claim_fortunewheelz_bonus(ctx, driver, channel)
        return

    print("[Fortune Wheelz] Attempting to login...")

    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Fortune Wheelz] Login button failed: {e}")

            try:
                print("[Fortune Wheelz] Trying direct signin URL...")
                driver.get(LOGIN_URL)
                await asyncio.sleep(5)
            except Exception:
                pass

        try:
            email = _wait_present(driver, By.XPATH, EMAIL_INPUT_XPATH, timeout=10)
            email.clear()
            email.send_keys(username)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Fortune Wheelz] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Fortune Wheelz] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "login submit button")
            print("[Fortune Wheelz] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Fortune Wheelz] Submit failed: {e}")

        _close_popups(driver)

        await claim_fortunewheelz_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print("[Fortune Wheelz] Login timeout:", e)

        await _send_screenshot(
            channel,
            driver,
            "Fortune Wheelz login timed out.",
            "fortunewheelz_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_fortunewheelz_bonus(ctx, driver, channel):
    print("[Fortune Wheelz] Navigating to promotions...")

    try:
        driver.get(PROMOTIONS_URL)
        await asyncio.sleep(8)
    except Exception as e:
        print(f"[Fortune Wheelz] Promotions navigation error: {e}")

    _close_popups(driver)

    # Keep the refresh behavior from the working claim version,
    # but check countdown after each refresh so we do not click a "Next in" button.
    for i in range(1, 4):
        print(f"[Fortune Wheelz] Checking countdown before refresh pass {i}...")

        countdown = _read_countdown(driver)
        if countdown:
            await _send_screenshot(
                channel,
                driver,
                f"Next Fortune Wheelz Bonus Available in: {countdown}",
                "fortunewheelz_countdown.png"
            )
            return

        print(f"[Fortune Wheelz] Refreshing promotions pass {i}...")

        try:
            driver.refresh()
            await asyncio.sleep(8)
            _close_popups(driver)
        except Exception as e:
            print(f"[Fortune Wheelz] Refresh pass {i} failed: {e}")

    # Final countdown check after refreshes.
    countdown = _read_countdown(driver)
    if countdown:
        await _send_screenshot(
            channel,
            driver,
            f"Next Fortune Wheelz Bonus Available in: {countdown}",
            "fortunewheelz_countdown.png"
        )
        return

    # Find the daily reward card/button.
    print("[Fortune Wheelz] Looking for daily reward promo button...")

    reward = _find_daily_reward_button(driver)

    if not reward:
        print("[Fortune Wheelz] Daily reward promo button not found.")
        await _send_countdown_or_unavailable(channel, driver)
        return

    reward_text = _element_text(driver, reward)
    print(f"[Fortune Wheelz] Daily reward button text: {reward_text!r}")

    # Hard stop: do NOT click if it is a countdown/disabled-looking card.
    if _button_looks_disabled(driver, reward):
        countdown = _normalize_countdown(reward_text) or _read_countdown(driver)

        if countdown:
            await _send_screenshot(
                channel,
                driver,
                f"Next Fortune Wheelz Bonus Available in: {countdown}",
                "fortunewheelz_countdown.png"
            )
            return

        await _send_screenshot(
            channel,
            driver,
            "Fortune Wheelz Daily Bonus Unavailable.",
            "fortunewheelz_claim_error.png"
        )
        return

    # Open the daily reward modal/card only if it does NOT say Next in.
    print("[Fortune Wheelz] Attempting to click daily reward promo button...")

    if not _safe_click(driver, reward, "daily reward promo button"):
        print("[Fortune Wheelz] Could not click daily reward promo button.")
        await _send_countdown_or_unavailable(channel, driver)
        return

    await asyncio.sleep(5)

    # Sometimes the modal opens and shows a countdown instead of claim.
    countdown = _read_countdown(driver)
    if countdown:
        await _send_screenshot(
            channel,
            driver,
            f"Next Fortune Wheelz Bonus Available in: {countdown}",
            "fortunewheelz_countdown.png"
        )
        return

    # Click the final daily-login claim button.
    print("[Fortune Wheelz] Attempting to claim daily bonus...")

    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        claim_text = _element_text(driver, claim)
        print(f"[Fortune Wheelz] Final claim button text: {claim_text!r}")

        if _button_looks_disabled(driver, claim):
            print("[Fortune Wheelz] Final claim button looks disabled/countdown. Not clicking.")
            await _send_countdown_or_unavailable(channel, driver)
            return

        if not _safe_click(driver, claim, "daily login claim button"):
            raise Exception("Could not click daily login claim button.")

        await asyncio.sleep(5)

        await _send_screenshot(
            channel,
            driver,
            "Fortune Wheelz Daily Bonus Claimed!",
            "fortunewheelz_claim.png"
        )

    except Exception as e:
        print("[Fortune Wheelz] Claim failed:", e)

        await _send_countdown_or_unavailable(channel, driver)


# ───────────────────────────────────────────────────────────
# Backwards Compatibility
# ───────────────────────────────────────────────────────────

async def fortunewheelz_flow(ctx, driver, channel):
    """
    Backwards-compatible wrapper for older main.py versions.
    """
    await fortunewheelz_casino(ctx, driver, channel)