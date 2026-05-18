# Drake Hooks + WaterTrooper
# Casino Claim 3
# Fortune Wheelz API
# Version 3.8
# Updated 2026.05.13
#
# Notes:
# - Handles the case where the modal has BOTH:
#     1) a valid claim button
#     2) an "available for HH:MM:SS" timer
# - Does NOT mistake "REWARD IS AVAILABLE FOR HH:MM:SS" as the next-claim countdown.
# - Finds newer card countdown text like:
#     "Next reward in 08:09:01"
# - Only treats "Next in", "Next reward in", "come back", etc. as unavailable countdowns.
# - Countdown sends text only — no screenshot.
# - Screenshots on successful claim, login timeout, or real error/no countdown candidate.
# - Keeps backwards compatibility with main.py by exposing both:
#     fortunewheelz_casino()
#     fortunewheelz_flow()

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

# Daily reward promo-card container.
DAILY_REWARD_CARD_XPATH = (
    "//div[@data-tid='promo-daily-login-card' "
    "or contains(@data-tid, 'daily-login-card') "
    "or contains(@data-tid, 'promo-daily-login')]"
)

# Final claim button inside the Daily Reward modal.
CLAIM_BUTTON_XPATH = "//button[@data-tid='daily-login-btn']"

# Final claim button fallbacks.
CLAIM_BUTTON_LOCATORS = [
    (By.XPATH, "//button[@data-tid='daily-login-btn']"),

    (
        By.XPATH,
        "//div[@id='ModalDailyLogin']//button["
        "contains(translate(normalize-space(.), "
        "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'COLLECT') "
        "or contains(translate(normalize-space(.), "
        "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'CLAIM')]"
    ),

    # Known modal absolute fallback.
    (By.XPATH, "/html/body/div[4]/div/div[2]/div[3]/button"),

    # Other common modal index fallbacks.
    (By.XPATH, "/html/body/div[3]/div/div[2]/div[3]/button"),
    (By.XPATH, "/html/body/div[5]/div/div[2]/div[3]/button"),
    (By.XPATH, "/html/body/div[6]/div/div[2]/div[3]/button"),
    (By.XPATH, "/html/body/div[7]/div/div[2]/div[3]/button"),
    (By.XPATH, "/html/body/div[8]/div/div[2]/div[3]/button"),
    (By.XPATH, "/html/body/div[9]/div/div[2]/div[3]/button"),

    (
        By.XPATH,
        "//button["
        "contains(translate(normalize-space(.), "
        "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'COLLECT TODAY') "
        "or contains(translate(normalize-space(.), "
        "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'COLLECT') "
        "or contains(translate(normalize-space(.), "
        "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'CLAIM')]"
    ),
]

# Exact daily reward card countdown paths.
# Includes newer card-header countdown:
# <p class="p4-medium uppercase color-overlay-white-060">Next reward in 08:09:01</p>
DAILY_CARD_COUNTDOWN_XPATHS = [
    # New card header countdown XPath from screenshot.
    "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[4]/div/div[1]/div[1]/div/p",

    # Older disabled button countdown paths.
    "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[4]/div/div[1]/div[2]/button",
    "/html/body/div[1]/div/div/div[2]/main/div/div[1]/div[2]/div[3]/div/div[1]/div[2]/button",
]

# Modal text fallbacks are only checked AFTER claim button fails.
# We explicitly ignore "REWARD IS AVAILABLE FOR HH:MM:SS".
MODAL_COUNTDOWN_XPATHS = [
    "/html/body/div[3]/div/div[2]/div[3]/p",
    "/html/body/div[4]/div/div[2]/div[3]/p",
    "/html/body/div[5]/div/div[2]/div[3]/p",
    "/html/body/div[6]/div/div[2]/div[3]/p",
    "/html/body/div[7]/div/div[2]/div[3]/p",
    "/html/body/div[8]/div/div[2]/div[3]/p",
    "/html/body/div[9]/div/div[2]/div[3]/p",
    "//*[@id='ModalDailyLogin']//*[contains(normalize-space(.), ':')]",
]

# Card-only next-claim countdown locators.
CARD_NEXT_COUNTDOWN_LOCATORS = [
    *[(By.XPATH, xp) for xp in DAILY_CARD_COUNTDOWN_XPATHS],

    # Best current selector for the new p-based timer.
    (
        By.XPATH,
        DAILY_REWARD_CARD_XPATH
        + "//*[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next reward') "
        "and contains(normalize-space(.), ':')]"
    ),

    # Specific class pattern from screenshot.
    (
        By.XPATH,
        "//p[contains(@class, 'p4-medium') "
        "and contains(@class, 'uppercase') "
        "and contains(@class, 'color-overlay-white') "
        "and contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next reward') "
        "and contains(normalize-space(.), ':')]"
    ),

    # More flexible text-only fallback for this exact copy.
    (
        By.XPATH,
        "//*[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next reward in') "
        "and contains(normalize-space(.), ':')]"
    ),

    # Older button countdown.
    (
        By.XPATH,
        "//button[@data-tid='promo-daily-login-button' "
        "and (contains(normalize-space(.), 'Next in') "
        "or contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next reward') "
        "or contains(normalize-space(.), ':'))]"
    ),

    (
        By.XPATH,
        "//button[@data-tid='promo-daily-login-button' "
        "and contains(@class, 'disabled') "
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
      - Next reward in 08:09:01
      - Next in 02:45:59
      - 02:45:59
      - 2 : 45 : 59

    Returns:
      - HH:MM:SS
      - None
    """
    if not text:
        return None

    # Handle &nbsp; / non-breaking spaces.
    text = text.replace("\xa0", " ")

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

    combined = " ".join(t.strip() for t in texts if t and t.strip()).strip()
    return combined.replace("\xa0", " ")


def _element_has_disabled_marker(element) -> bool:
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

    return False


def _extract_next_claim_countdown(text: str, allow_bare_time: bool = False) -> str | None:
    """
    Extracts ONLY a next-claim countdown.

    It intentionally ignores:
      - "REWARD IS AVAILABLE FOR 22:57:59"
      - "available for HH:MM:SS"

    Because that timer means the current claim is still available,
    not that the next claim is locked.
    """
    if not text:
        return None

    raw = " ".join(text.replace("\xa0", " ").split())
    lower = raw.lower()

    countdown = _normalize_countdown(raw)

    if not countdown:
        return None

    # Critical distinction:
    # This is NOT the next-claim countdown.
    if "available for" in lower:
        return None

    next_claim_phrases = [
        "next in",
        "next reward",
        "next reward in",
        "next bonus",
        "available in",
        "come back",
        "tomorrow",
        "claim again",
        "unavailable",
        "cooldown",
    ]

    if any(phrase in lower for phrase in next_claim_phrases):
        return countdown

    if allow_bare_time:
        return countdown

    return None


def _button_is_next_claim_countdown(driver, element) -> bool:
    text = _element_text(driver, element)
    disabled = _element_has_disabled_marker(element)

    if _extract_next_claim_countdown(text, allow_bare_time=disabled):
        return True

    return False


def _read_next_claim_countdown(driver, include_modal: bool = False) -> str | None:
    """
    Reads ONLY the next-claim countdown.

    Card countdown is safe before claim.
    Modal countdown is only safe after claim button fails, because the modal
    can contain "REWARD IS AVAILABLE FOR HH:MM:SS" while the claim is still valid.
    """
    locators = list(CARD_NEXT_COUNTDOWN_LOCATORS)

    if include_modal:
        locators.extend((By.XPATH, xp) for xp in MODAL_COUNTDOWN_XPATHS)

    best_candidate = None

    for by, value in locators:
        try:
            elements = driver.find_elements(by, value)

            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                except Exception:
                    pass

                try:
                    text = _element_text(driver, element)
                    disabled = _element_has_disabled_marker(element)

                    countdown = _extract_next_claim_countdown(
                        text,
                        allow_bare_time=disabled
                    )

                    if countdown:
                        print(
                            f"[Fortune Wheelz] Next-claim countdown found: "
                            f"{countdown} from text: {text!r}"
                        )
                        return countdown

                    # Keep a safe fallback candidate if the locator was already
                    # card-scoped and text is only HH:MM:SS.
                    if not best_candidate:
                        bare = _normalize_countdown(text)
                        lower = text.lower()

                        if bare and "available for" not in lower:
                            best_candidate = bare

                except Exception:
                    continue

        except Exception:
            continue

    if best_candidate:
        print(f"[Fortune Wheelz] Using fallback countdown candidate: {best_candidate}")
        return best_candidate

    return None


def _find_daily_reward_button(driver):
    """
    Finds the Fortune Wheelz daily login promo button.
    This can be either:
      - Available claim button
      - Disabled-looking countdown button.
    """
    try:
        buttons = driver.find_elements(By.XPATH, CLAIM_REWARD_XPATH)
    except Exception:
        return None

    if not buttons:
        return None

    for btn in buttons:
        try:
            if btn.is_displayed():
                return btn
        except Exception:
            continue

    return buttons[0]


def _find_final_claim_button(driver, timeout_per_locator=3):
    """
    Finds the modal's real claim button.
    This must run BEFORE reading modal countdowns because the modal can show
    an availability timer while the claim button is valid.
    """
    for by, value in CLAIM_BUTTON_LOCATORS:
        try:
            button = WebDriverWait(driver, timeout_per_locator).until(
                EC.presence_of_element_located((by, value))
            )

            try:
                if not button.is_displayed():
                    continue
            except Exception:
                pass

            text = _element_text(driver, button)
            print(f"[Fortune Wheelz] Claim button candidate text: {text!r}")

            if _button_is_next_claim_countdown(driver, button):
                print("[Fortune Wheelz] Candidate is a next-countdown button, not claim.")
                continue

            if _element_has_disabled_marker(button):
                print("[Fortune Wheelz] Candidate has disabled marker, skipping.")
                continue

            return button

        except TimeoutException:
            continue
        except Exception as e:
            print(f"[Fortune Wheelz] Claim button locator failed: {value} | {e}")
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


async def _send_countdown(channel, countdown: str):
    """
    Countdown should be text only.
    No screenshot here.
    """
    await channel.send(f"Next Fortune Wheelz Bonus Available in: {countdown}")


async def _send_countdown_or_unavailable(channel, driver, include_modal: bool = False):
    """
    Sends next-claim countdown as plain text if found.
    Screenshots only if no countdown candidate can be found.
    """
    countdown = _read_next_claim_countdown(driver, include_modal=include_modal)

    if countdown:
        await _send_countdown(channel, countdown)
        return True

    await _send_screenshot(
        channel,
        driver,
        "Fortune Wheelz Daily Bonus Unavailable. Could not find a valid next-claim countdown candidate.",
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

    # Keep the refresh behavior from the working claim version.
    # Only read CARD next-claim countdown here.
    # Do NOT read modal availability timers before trying claim.
    for i in range(1, 4):
        print(f"[Fortune Wheelz] Checking card next-claim countdown before refresh pass {i}...")

        countdown = _read_next_claim_countdown(driver, include_modal=False)

        if countdown:
            await _send_countdown(channel, countdown)
            return

        print(f"[Fortune Wheelz] Refreshing promotions pass {i}...")

        try:
            driver.refresh()
            await asyncio.sleep(8)
            _close_popups(driver)
        except Exception as e:
            print(f"[Fortune Wheelz] Refresh pass {i} failed: {e}")

    # Final card-only countdown check after refreshes.
    countdown = _read_next_claim_countdown(driver, include_modal=False)

    if countdown:
        await _send_countdown(channel, countdown)
        return

    print("[Fortune Wheelz] Looking for daily reward promo button...")

    reward = _find_daily_reward_button(driver)

    if not reward:
        print("[Fortune Wheelz] Daily reward promo button not found.")
        await _send_countdown_or_unavailable(channel, driver, include_modal=False)
        return

    reward_text = _element_text(driver, reward)
    print(f"[Fortune Wheelz] Daily reward button text: {reward_text!r}")

    # Hard stop: do NOT click if the card is a next-claim countdown.
    if _button_is_next_claim_countdown(driver, reward):
        countdown = _extract_next_claim_countdown(
            reward_text,
            allow_bare_time=_element_has_disabled_marker(reward)
        ) or _read_next_claim_countdown(driver, include_modal=False)

        if countdown:
            await _send_countdown(channel, countdown)
            return

        await _send_screenshot(
            channel,
            driver,
            "Fortune Wheelz Daily Bonus Unavailable. Daily reward card looked unavailable, but no valid next-claim countdown was found.",
            "fortunewheelz_claim_error.png"
        )
        return

    if _element_has_disabled_marker(reward):
        print("[Fortune Wheelz] Daily reward button has disabled marker.")
        await _send_countdown_or_unavailable(channel, driver, include_modal=False)
        return

    print("[Fortune Wheelz] Attempting to click daily reward promo button...")

    if not _safe_click(driver, reward, "daily reward promo button"):
        print("[Fortune Wheelz] Could not click daily reward promo button.")
        await _send_countdown_or_unavailable(channel, driver, include_modal=False)
        return

    await asyncio.sleep(5)

    # Try final claim button BEFORE reading modal countdown text.
    print("[Fortune Wheelz] Looking for final modal claim button...")

    claim = _find_final_claim_button(driver, timeout_per_locator=3)

    if claim:
        try:
            claim_text = _element_text(driver, claim)
            print(f"[Fortune Wheelz] Final claim button text: {claim_text!r}")

            if not _safe_click(driver, claim, "daily login claim button"):
                raise Exception("Could not click daily login claim button.")

            await asyncio.sleep(5)

            await _send_screenshot(
                channel,
                driver,
                "Fortune Wheelz Daily Bonus Claimed!",
                "fortunewheelz_claim.png"
            )
            return

        except Exception as e:
            print(f"[Fortune Wheelz] Final claim click failed: {e}")

    print("[Fortune Wheelz] Final claim button not found/clickable. Checking true next-claim countdown...")

    await _send_countdown_or_unavailable(channel, driver, include_modal=True)


# ───────────────────────────────────────────────────────────
# Backwards Compatibility
# ───────────────────────────────────────────────────────────

async def fortunewheelz_flow(ctx, driver, channel):
    """
    Backwards-compatible wrapper for older main.py versions.
    """
    await fortunewheelz_casino(ctx, driver, channel)