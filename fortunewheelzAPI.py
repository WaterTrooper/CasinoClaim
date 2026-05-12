# Drake Hooks + WaterTrooper
# Casino Claim 3
# Fortune Wheelz API
# Version 3.4
# Updated 2026.05.12
#
# Notes:
# - Based on WT's latest working claim flow.
# - Adds countdown detection when daily bonus is unavailable.
# - Keeps screenshots for claim, countdown/unavailable, and login timeout.

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

CLAIM_REWARD_XPATH = "//button[@data-tid='promo-daily-login-button']"
CLAIM_BUTTON_XPATH = "//button[@data-tid='daily-login-btn']"

# Countdown fallbacks
COUNTDOWN_LOCATORS = [
    # Modal countdown text from older working countdown version
    (By.XPATH, "/html/body/div[4]/div/div[2]/div[3]/p"),
    (By.XPATH, "/html/body/div[3]/div/div[2]/div[3]/p"),
    (By.XPATH, "/html/body/div[5]/div/div[2]/div[3]/p"),
    (By.XPATH, "/html/body/div[8]/div/div[2]/div[3]/p"),
    (By.XPATH, "/html/body/div[9]/div/div[2]/div[3]/p"),

    # Disabled store/promo button absolute fallback from older version
    (
        By.XPATH,
        "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[3]/div/div[1]/div[2]/button"
    ),

    # Generic disabled button with HH:MM:SS text
    (
        By.XPATH,
        "//button[@disabled and contains(normalize-space(.), ':')]"
    ),

    # Generic element containing HH:MM:SS text
    (
        By.XPATH,
        "//*[contains(normalize-space(.), ':')]"
    ),
]

POPUP_CLOSE_XPATHS = [
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
    Accepts strings like:
      - 22 : 27 : 06
      - 22:27:06
      - Come back in 22:27:06

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


def _read_countdown(driver) -> str | None:
    """
    Attempts to find countdown from:
      1. Daily login modal paragraph
      2. Disabled promo/store button
      3. Generic disabled button containing HH:MM:SS
      4. Generic visible page element containing HH:MM:SS
    """
    for by, value in COUNTDOWN_LOCATORS:
        try:
            elements = driver.find_elements(by, value)

            for element in elements:
                try:
                    text = (element.text or "").strip()
                    countdown = _normalize_countdown(text)

                    if countdown:
                        print(f"[Fortune Wheelz] Countdown found: {countdown}")
                        return countdown

                except Exception:
                    continue

        except Exception:
            continue

    return None


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
                    asyncio.sleep(1)

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

            # Fallback: go directly to signin page
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
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Fortune Wheelz] Promotions navigation error: {e}")

    _close_popups(driver)

    # This refresh pattern is from the newer working claim code.
    for i in range(1, 4):
        print(f"[Fortune Wheelz] Refreshing promotions pass {i}...")
        try:
            driver.refresh()
            await asyncio.sleep(10)
            _close_popups(driver)
        except Exception as e:
            print(f"[Fortune Wheelz] Refresh pass {i} failed: {e}")

    # Try to open the daily login reward modal/card.
    print("[Fortune Wheelz] Attempting to click claim reward button...")

    try:
        reward = _wait_clickable(driver, By.XPATH, CLAIM_REWARD_XPATH, timeout=10)
        _safe_click(driver, reward, "claim reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Fortune Wheelz] Reward button failed: {e}")

        # If reward button is disabled/unavailable, try countdown immediately.
        countdown = _read_countdown(driver)

        if countdown:
            await _send_screenshot(
                channel,
                driver,
                f"Next Fortune Wheelz Bonus Available in: {countdown}",
                "fortunewheelz_countdown.png"
            )
            return

    # Try the final daily-login claim button.
    print("[Fortune Wheelz] Attempting to claim daily bonus...")

    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)

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