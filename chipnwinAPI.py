# Drake Hooks + WaterTrooper
# Casino Claim 3
# Chipnwin API
# Version 5.0
# Updated 2026.05.13
#
# Notes:
# - Adds direct rewards page support:
#     https://chipnwin.com/store/features/#/rewards
# - Reads Daily Rewards countdown BEFORE trying to claim.
# - Uses a candidate system to find the current-day countdown.
# - Countdown sends text only — no screenshot.
# - Only sends "claimed" if the claim click is confirmed.
# - Screenshots on successful claim, login timeout, or real error/no countdown candidate.

import re
import os
import asyncio
import discord
from dotenv import load_dotenv

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)


# ───────────────────────────────────────────────────────────
# Config & Constants
# ───────────────────────────────────────────────────────────

load_dotenv()

CHIPNWIN_CRED = os.getenv("CHIPNWIN")  # format "email:password"

SITE_URL = "https://chipnwin.com"
STORE_URL = "https://chipnwin.com/store/features"
REWARDS_URL = "https://chipnwin.com/store/features/#/rewards"

COOKIE_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/button",
    "/html/body/div[1]/div[7]/div/div[2]/button",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
]

LOGIN_BUTTON_XPATH = "//span[@class='s14__w500__h22 color_ADADC2']"
EMAIL_INPUT_XPATH = "//input[@id='input_customemail']"
PASSWORD_INPUT_XPATH = "//input[@id='input_custompassword']"

LOGIN_SUBMIT_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[5]/div/button",
    "/html/body/div[1]/div[7]/div/div[2]/div[2]/div[5]/div/button",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
]

START_BUTTON_XPATHS = [
    "/html/body/div[1]/div[3]/div/div[1]/div[3]/div[2]/div[3]/div[4]/div[2]/button",
    "/html/body/div[1]/div[4]/div/div[1]/div[3]/div[2]/div[3]/div[4]/div[2]/button",

    # Generic daily reward openers.
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily')]",
    "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]",
    "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily reward')]",
]

CLAIM_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/div[3]/button",
    "/html/body/div[1]/div[7]/div/div[2]/div[3]/button",
    "/html/body/div[1]/div[8]/div/div[2]/div[3]/button",

    # Generic modal claim buttons.
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]",
    "//div[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]",
]

SPINWIN_BUTTON_XPATHS = [
    "/html/body/div[1]/div[3]/div/div[1]/div[3]/div[2]/div[2]/div[4]/div[2]/button",
    "/html/body/div[1]/div[4]/div/div[1]/div[3]/div[2]/div[2]/div[4]/div[2]/button",
]

SPIN_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[3]/div/button",
    "/html/body/div[1]/div[7]/div/div[3]/div/button",
]

# Your current-day countdown XPath fallback.
CURRENT_DAY_COUNTDOWN_XPATH = "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[1]/p"

# Countdown candidates.
# Keep these focused on the Daily Rewards modal/card so it does not grab random timers.
COUNTDOWN_CANDIDATE_LOCATORS = [
    (By.XPATH, CURRENT_DAY_COUNTDOWN_XPATH),

    # Best match from your element:
    # <p class="s14__w500__h22 ... text_align_center white_space_nowrap ...">22:56:23</p>
    (
        By.XPATH,
        "//p[contains(@class, 's14__w500__h22') "
        "and contains(@class, 'text_align_center') "
        "and contains(@class, 'white_space_nowrap') "
        "and contains(normalize-space(.), ':')]"
    ),

    # Current active daily reward card tends to be first normal daily-rewards card.
    (
        By.XPATH,
        "//div[contains(@class, 'daily-rewards__card')][1]"
        "//p[contains(normalize-space(.), ':')]"
    ),

    # Modal-scoped p countdowns.
    (
        By.XPATH,
        "//div[contains(@class, 'layouts-modals-simple') "
        "or contains(@class, 'modal') "
        "or contains(@class, 'fixed')]"
        "//p[contains(normalize-space(.), ':')]"
    ),

    # Daily rewards scoped fallback.
    (
        By.XPATH,
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]"
        "/ancestor::div[1]//p[contains(normalize-space(.), ':')]"
    ),

    # Last resort: visible p elements with a clean HH:MM:SS format.
    (
        By.XPATH,
        "//p[contains(normalize-space(.), ':')]"
    ),
]


# ───────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(
            By.XPATH,
            "//p[@class='s12__w500__h18 color_1BB83D line_height_normal_important']"
        )
        return True
    except NoSuchElementException:
        pass

    try:
        driver.find_element(By.XPATH, "//span[@data-test='balance']")
        return True
    except NoSuchElementException:
        pass

    try:
        driver.find_element(
            By.XPATH,
            "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'wallet')]"
        )
        return True
    except NoSuchElementException:
        return False


def _clean_countdown(raw: str) -> str | None:
    """
    Accepts:
      - 22:56:23
      - 22 : 56 : 23

    Returns:
      - HH:MM:SS
      - None
    """
    if not raw:
        return None

    match = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*:\s*(\d{2})", raw)

    if not match:
        return None

    h, m, s = match.groups()
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"


def _element_text(driver, el) -> str:
    texts = []

    try:
        texts.append(el.text or "")
    except Exception:
        pass

    try:
        texts.append(driver.execute_script("return arguments[0].innerText || '';", el) or "")
    except Exception:
        pass

    try:
        texts.append(driver.execute_script("return arguments[0].textContent || '';", el) or "")
    except Exception:
        pass

    return " ".join(t.strip() for t in texts if t and t.strip()).strip()


def _scroll_into_view(driver, el) -> None:
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            el
        )
    except Exception:
        pass


def _safe_click(driver, el, label="element") -> bool:
    try:
        _scroll_into_view(driver, el)
        el.click()
        print(f"[Chipnwin] Clicked {label}.")
        return True
    except (ElementClickInterceptedException, Exception) as e:
        print(f"[Chipnwin] Normal click failed for {label}: {e}")

    try:
        _scroll_into_view(driver, el)
        driver.execute_script("arguments[0].click();", el)
        print(f"[Chipnwin] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[Chipnwin] JS click failed for {label}: {e}")
        return False


def _first_clickable(driver, xpaths, timeout=6):
    """
    Returns (xpath, element) for first clickable XPath.
    """
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            return xp, el
        except TimeoutException:
            continue
        except Exception:
            continue

    return None, None


def _element_disabled_or_not_allowed(driver, el) -> bool:
    try:
        classes = (el.get_attribute("class") or "").lower()

        if "disabled" in classes or "not_allowed" in classes or "not-allowed" in classes:
            return True
    except Exception:
        pass

    for attr in ("disabled", "aria-disabled"):
        try:
            value = (el.get_attribute(attr) or "").strip().lower()

            if value in {"true", "1", "disabled"}:
                return True
        except Exception:
            pass

    return False


def _score_countdown_candidate(driver, el, text: str) -> int:
    score = 0

    try:
        tag = (el.tag_name or "").lower()
        if tag == "p":
            score += 20
    except Exception:
        pass

    try:
        classes = (el.get_attribute("class") or "").lower()

        if "s14__w500__h22" in classes:
            score += 30
        if "text_align_center" in classes:
            score += 20
        if "white_space_nowrap" in classes:
            score += 20
        if "background_914bfa" in classes:
            score += 20
        if "daily-rewards" in classes:
            score += 15
    except Exception:
        pass

    try:
        nearby_text = driver.execute_script(
            """
            let e = arguments[0];
            let out = '';
            for (let i = 0; e && i < 6; i++, e = e.parentElement) {
                out += ' ' + (e.innerText || '');
            }
            return out;
            """,
            el
        ) or ""

        nearby_lower = nearby_text.lower()

        if "daily rewards" in nearby_lower:
            score += 30
        if "log in daily" in nearby_lower:
            score += 20
        if "claim prizes" in nearby_lower:
            score += 15
        if "spin" in nearby_lower or "wheel" in nearby_lower:
            score -= 15
    except Exception:
        pass

    # Clean HH:MM:SS text is better than a big blob of text.
    if re.fullmatch(r"\s*\d{1,2}\s*:\s*\d{2}\s*:\s*\d{2}\s*", text or ""):
        score += 40
    elif _clean_countdown(text):
        score += 10

    return score


def _read_countdown(driver, timeout=8) -> str | None:
    """
    Candidate-system countdown reader.

    This searches for likely Daily Rewards countdown elements, scores them,
    and returns the best HH:MM:SS candidate.
    """
    end_time = asyncio.get_event_loop().time() + timeout if asyncio.get_event_loop().is_running() else None

    candidates = []
    seen = set()

    # Do a few short passes because the modal often animates in.
    passes = max(1, int(timeout / 2))

    for _ in range(passes):
        for by, value in COUNTDOWN_CANDIDATE_LOCATORS:
            try:
                elements = driver.find_elements(by, value)

                for el in elements:
                    try:
                        remote_id = getattr(el, "id", None) or str(el)

                        if remote_id in seen:
                            continue

                        seen.add(remote_id)

                        if not el.is_displayed():
                            continue

                        text = _element_text(driver, el)
                        countdown = _clean_countdown(text)

                        if not countdown:
                            continue

                        score = _score_countdown_candidate(driver, el, text)
                        candidates.append((score, countdown, text))

                    except StaleElementReferenceException:
                        continue
                    except Exception:
                        continue

            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_countdown, best_text = candidates[0]
            print(
                f"[Chipnwin] Countdown candidate selected: {best_countdown} "
                f"(score={best_score}, text={best_text!r})"
            )
            return best_countdown

        try:
            import time
            time.sleep(2)
        except Exception:
            break

        if end_time and asyncio.get_event_loop().time() >= end_time:
            break

    return None


async def _send_countdown(channel, countdown: str):
    await channel.send(f"Next Chipnwin Bonus Available in: {countdown}")


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[Chipnwin] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


def _daily_rewards_modal_open(driver) -> bool:
    checks = [
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in daily to claim prizes')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]",
    ]

    for xp in checks:
        try:
            elements = driver.find_elements(By.XPATH, xp)

            for el in elements:
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue

        except Exception:
            continue

    return False


async def _open_daily_rewards(driver):
    """
    Opens the Daily Rewards modal/page.

    First tries the direct hash route:
      /store/features/#/rewards

    If the modal does not open, falls back to clicking Daily Rewards card.
    """
    print("[Chipnwin] Navigating directly to rewards page...")
    driver.get(REWARDS_URL)
    await asyncio.sleep(6)

    if _daily_rewards_modal_open(driver):
        print("[Chipnwin] Daily Rewards modal/page opened from direct link.")
        return True

    print("[Chipnwin] Direct rewards route did not open modal. Trying store card...")
    driver.get(STORE_URL)
    await asyncio.sleep(5)

    _, start_btn = _first_clickable(driver, START_BUTTON_XPATHS, timeout=8)

    if start_btn:
        if _safe_click(driver, start_btn, "daily rewards card"):
            await asyncio.sleep(5)

            if _daily_rewards_modal_open(driver):
                print("[Chipnwin] Daily Rewards modal opened from card.")
                return True

    print("[Chipnwin] Could not confirm Daily Rewards modal/page is open.")
    return False


def _confirm_claim_succeeded(driver, clicked_element, timeout=8) -> bool:
    """
    Only announce claimed if we see a real post-click success state.

    Removed the old broad "reward" success check because the Daily Rewards modal
    itself always contains that word and caused false positives.
    """
    try:
        WebDriverWait(driver, timeout).until(EC.staleness_of(clicked_element))
        return True
    except TimeoutException:
        pass
    except Exception:
        pass

    try:
        before = (clicked_element.text or "").strip().lower()

        def _btn_changed(_driver):
            try:
                txt = (clicked_element.text or "").strip().lower()

                if "claimed" in txt:
                    return True

                if before and txt and txt != before and "claim" not in txt:
                    return True

                return False
            except Exception:
                return False

        if WebDriverWait(driver, timeout).until(_btn_changed):
            return True
    except TimeoutException:
        pass
    except Exception:
        pass

    success_xpaths = [
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claimed')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'success')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'congrat')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collected')]",
    ]

    for xp in success_xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xp)

            for el in elements:
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue

        except Exception:
            continue

    return False


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def chipnwin_casino(ctx, driver, channel):
    if not CHIPNWIN_CRED:
        await channel.send("❌ Missing `CHIPNWIN` as 'email:password' in your .env.")
        return

    username, password = CHIPNWIN_CRED.split(":", 1)

    print("[Chipnwin] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)

    print("[Chipnwin] Attempting to accept cookie...")
    for cb in COOKIE_BUTTON_XPATHS:
        try:
            cookie = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, cb))
            )

            if _safe_click(driver, cookie, "cookie button"):
                await asyncio.sleep(3)
                break

        except TimeoutException:
            pass
        except Exception:
            pass

    if _is_logged_in(driver):
        print("[Chipnwin] Already logged in. Using direct rewards URL.")
        await claim_chipnwin_bonus(ctx, driver, channel)
        return

    print("[Chipnwin] Attempting to login...")

    try:
        try:
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, LOGIN_BUTTON_XPATH))
            )
            _safe_click(driver, login_btn, "login button")
            await asyncio.sleep(8)
        except Exception as e:
            print(f"[Chipnwin] Login button failed: {e}")

        try:
            email = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, EMAIL_INPUT_XPATH))
            )
            email.clear()
            email.send_keys(username)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Chipnwin] Email input failed: {e}")

        try:
            pw = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, PASSWORD_INPUT_XPATH))
            )
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Chipnwin] Password input failed: {e}")

        submitted = False

        for ls in LOGIN_SUBMIT_XPATHS:
            try:
                btn = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((By.XPATH, ls))
                )

                if _safe_click(driver, btn, "login submit button"):
                    submitted = True
                    print("[Chipnwin] Submitted credentials.")
                    await asyncio.sleep(10)
                    break

            except Exception:
                continue

        if not submitted:
            print("[Chipnwin] Submit failed.")

        print("[Chipnwin] Reloading site once...")
        driver.refresh()
        await asyncio.sleep(5)

        await claim_chipnwin_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print("[Chipnwin] Login timeout:", e)

        await _send_screenshot(
            channel,
            driver,
            "Chipnwin login timed out.",
            "chipnwin_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_chipnwin_bonus(ctx, driver, channel):
    print("[Chipnwin] Opening Daily Rewards...")

    opened = await _open_daily_rewards(driver)

    if not opened:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] Could not open Daily Rewards page/modal.",
            "chipnwin_rewards_open_error.png"
        )
        return

    # Main requested behavior:
    # Read countdown FIRST. If there is a countdown, report it and stop.
    print("[Chipnwin] Searching for Daily Rewards countdown candidate before claiming...")
    countdown = _read_countdown(driver, timeout=10)

    if countdown:
        await _send_countdown(channel, countdown)
        return

    # If no countdown exists, then try claim.
    print("[Chipnwin] No countdown found. Attempting claim...")
    claimed = False

    claim_xpath, claim_btn = _first_clickable(driver, CLAIM_BUTTON_XPATHS, timeout=8)

    if claim_btn:
        if _element_disabled_or_not_allowed(driver, claim_btn):
            print("[Chipnwin] Claim button exists but looks disabled/not allowed.")

            # Try one more countdown read before treating it as a real error.
            countdown = _read_countdown(driver, timeout=5)

            if countdown:
                await _send_countdown(channel, countdown)
                return

            await _send_screenshot(
                channel,
                driver,
                "[Chipnwin] Claim button looked disabled, but no countdown candidate was found.",
                "chipnwin_claim_disabled_no_countdown.png"
            )
            return

        clicked = _safe_click(driver, claim_btn, "daily reward claim button")

        if clicked:
            await asyncio.sleep(2)

            if _confirm_claim_succeeded(driver, claim_btn, timeout=8):
                claimed = True

    if claimed:
        await _send_screenshot(
            channel,
            driver,
            "Chipnwin Daily Bonus Claimed!",
            "chipnwin_claim.png"
        )
        return

    # If claim did not confirm, try countdown one last time.
    countdown = _read_countdown(driver, timeout=8)

    if countdown:
        await _send_countdown(channel, countdown)
        return

    await _send_screenshot(
        channel,
        driver,
        "[Chipnwin] claim not available and could not read countdown candidate.",
        "chipnwin_claim_error.png"
    )


# ───────────────────────────────────────────────────────────
# 3) Standalone Countdown Reader
# ───────────────────────────────────────────────────────────

async def check_chipnwin_countdown(ctx, driver, channel):
    print("[Chipnwin] Opening Daily Rewards for countdown...")
    opened = await _open_daily_rewards(driver)

    if not opened:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] could not open Daily Rewards page/modal.",
            "chipnwin_countdown_open_error.png"
        )
        return

    print("[Chipnwin] Checking for countdown timer...")
    countdown = _read_countdown(driver, timeout=12)

    if countdown:
        await _send_countdown(channel, countdown)
    else:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] could not read countdown candidate.",
            "chipnwin_countdown_error.png"
        )


# ───────────────────────────────────────────────────────────
# 4) Daily Spin Wheel
# ───────────────────────────────────────────────────────────

async def spin_chipnwin_wheel(ctx, driver, channel):
    print("[Chipnwin] Navigating to store...")
    driver.get(STORE_URL)
    await asyncio.sleep(6)

    print("[Chipnwin] Opening Spin & Win...")
    _, spinwin_btn = _first_clickable(driver, SPINWIN_BUTTON_XPATHS, timeout=8)

    if spinwin_btn:
        _safe_click(driver, spinwin_btn, "spin & win card")
        await asyncio.sleep(4)
    else:
        print("[Chipnwin] Spin & Win card not found/clickable.")

    print("[Chipnwin] Attempting to spin the wheel...")
    _, spin_btn = _first_clickable(driver, SPIN_BUTTON_XPATHS, timeout=8)

    if spin_btn and _safe_click(driver, spin_btn, "spin button"):
        await channel.send("Chipnwin Wheel Spun!")
    else:
        await channel.send("[Chipnwin] spin not available or could not click.")