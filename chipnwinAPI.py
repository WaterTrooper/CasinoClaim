# Drake Hooks + WaterTrooper
# Casino Claim 3
# Chipnwin API
# Version 5.2
# Updated 2026.05.13
#
# Notes:
# - Fixes false "already logged in" detection.
# - Uses direct login URL:
#     https://chipnwin.com/#/login
# - Uses direct rewards URL:
#     https://chipnwin.com/store/features/#/rewards
# - Adds your exact email field XPath as the first email candidate.
# - Uses a robust candidate/scoring system for email/password fields.
# - Uses JS/native input events if normal send_keys does not stick.
# - Uses state-based flow:
#     rewards open -> claim/countdown
#     login form open -> login
#     unknown -> try login, then rewards
# - Reads Daily Rewards countdown if claim is unavailable.
# - Countdown sends text only — no screenshot.
# - Screenshots on successful claim, login failure, rewards-open failure, or no countdown/claim candidate.

import re
import os
import time
import asyncio
import discord
from dotenv import load_dotenv

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
LOGIN_URL = "https://chipnwin.com/#/login"
STORE_URL = "https://chipnwin.com/store/features"
REWARDS_URL = "https://chipnwin.com/store/features/#/rewards"

COOKIE_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/button",
    "/html/body/div[1]/div[7]/div/div[2]/button",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it')]",
]

# Exact field XPath from your screenshot.
EMAIL_EXACT_XPATH = "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[4]/div[1]/div[2]/div[1]/input"

# Best-guess absolute password fallback near the same modal structure.
PASSWORD_EXACT_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[4]/div[2]/div[2]/div[1]/input",
    "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[4]/div[2]/div[2]/input",
    "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[4]/div[2]//input",
    "/html/body/div[1]/div[7]/div/div[2]/div[2]/div[4]/div[2]//input",
]

EMAIL_FIELD_LOCATORS = [
    (By.XPATH, EMAIL_EXACT_XPATH),
    (By.ID, "input_customemail"),
    (By.CSS_SELECTOR, "input#input_customemail"),
    (By.CSS_SELECTOR, "input[type='email']"),
    (By.XPATH, "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"),
    (By.XPATH, "//input[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"),
    (By.XPATH, "//input[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"),
    (By.XPATH, "//input[contains(translate(@autocomplete, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"),
]

PASSWORD_FIELD_LOCATORS = [
    *[(By.XPATH, xp) for xp in PASSWORD_EXACT_XPATHS],
    (By.ID, "input_custompassword"),
    (By.CSS_SELECTOR, "input#input_custompassword"),
    (By.CSS_SELECTOR, "input[type='password']"),
    (By.XPATH, "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]"),
    (By.XPATH, "//input[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]"),
    (By.XPATH, "//input[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]"),
    (By.XPATH, "//input[contains(translate(@autocomplete, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]"),
]

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
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily')]",
    "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]",
    "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily reward')]",
]

CLAIM_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[2]/div[3]/button",
    "/html/body/div[1]/div[7]/div/div[2]/div[3]/button",
    "/html/body/div[1]/div[8]/div/div[2]/div[3]/button",
    "//div[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]",
]

SPINWIN_BUTTON_XPATHS = [
    "/html/body/div[1]/div[3]/div/div[1]/div[3]/div[2]/div[2]/div[4]/div[2]/button",
    "/html/body/div[1]/div[4]/div/div[1]/div[3]/div[2]/div[2]/div[4]/div[2]/button",
]

SPIN_BUTTON_XPATHS = [
    "/html/body/div[1]/div[6]/div/div[3]/div/button",
    "/html/body/div[1]/div[7]/div/div[3]/div/button",
]

CURRENT_DAY_COUNTDOWN_XPATH = "/html/body/div[1]/div[6]/div/div[2]/div[2]/div[1]/p"

COUNTDOWN_CANDIDATE_LOCATORS = [
    (By.XPATH, CURRENT_DAY_COUNTDOWN_XPATH),

    (
        By.XPATH,
        "//p[contains(@class, 's14__w500__h22') "
        "and contains(@class, 'text_align_center') "
        "and contains(@class, 'white_space_nowrap') "
        "and contains(normalize-space(.), ':')]"
    ),

    (
        By.XPATH,
        "//div[contains(@class, 'daily-rewards__card')][1]"
        "//p[contains(normalize-space(.), ':')]"
    ),

    (
        By.XPATH,
        "//div[contains(@class, 'layouts-modals-simple') "
        "or contains(@class, 'modal') "
        "or contains(@class, 'fixed')]"
        "//p[contains(normalize-space(.), ':')]"
    ),

    (
        By.XPATH,
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daily rewards')]"
        "/ancestor::div[1]//p[contains(normalize-space(.), ':')]"
    ),

    (
        By.XPATH,
        "//p[contains(normalize-space(.), ':')]"
    ),
]


# ───────────────────────────────────────────────────────────
# Generic Helpers
# ───────────────────────────────────────────────────────────

def _attr(el, name: str) -> str:
    try:
        return el.get_attribute(name) or ""
    except Exception:
        return ""


def _lower_attr(el, name: str) -> str:
    return _attr(el, name).strip().lower()


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

    return " ".join(t.strip() for t in texts if t and t.strip()).replace("\xa0", " ").strip()


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


def _is_visible(el) -> bool:
    try:
        return bool(el.is_displayed())
    except Exception:
        return False


def _is_enabled(el) -> bool:
    try:
        return bool(el.is_enabled())
    except Exception:
        return False


def _element_disabled_or_not_allowed(driver, el) -> bool:
    classes = _lower_attr(el, "class")

    if "disabled" in classes or "not_allowed" in classes or "not-allowed" in classes:
        return True

    for attr in ("disabled", "aria-disabled"):
        value = _lower_attr(el, attr)
        if value in {"true", "1", "disabled"}:
            return True

    return False


def _first_clickable(driver, xpaths, timeout=6):
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


async def _send_countdown(channel, countdown: str):
    await channel.send(f"Next Chipnwin Bonus Available in: {countdown}")


# ───────────────────────────────────────────────────────────
# Login Candidate System
# ───────────────────────────────────────────────────────────

def _score_input_candidate(driver, el, kind: str) -> int:
    score = 0

    if not _is_visible(el):
        return -999

    if not _is_enabled(el):
        return -999

    if _lower_attr(el, "readonly") in {"true", "readonly", "1"}:
        return -999

    try:
        tag = (el.tag_name or "").lower()
    except Exception:
        tag = ""

    if tag != "input":
        return -999

    typ = _lower_attr(el, "type")
    placeholder = _lower_attr(el, "placeholder")
    name = _lower_attr(el, "name")
    element_id = _lower_attr(el, "id")
    autocomplete = _lower_attr(el, "autocomplete")
    classes = _lower_attr(el, "class")

    if kind == "email":
        if typ == "email":
            score += 100
        if "customemail" in element_id:
            score += 120
        if "email" in element_id:
            score += 80
        if "email" in placeholder:
            score += 70
        if "email" in name:
            score += 60
        if "email" in autocomplete or "username" in autocomplete:
            score += 30
        if typ in {"password", "checkbox", "hidden", "submit", "button"}:
            score -= 300

    if kind == "password":
        if typ == "password":
            score += 120
        if "custompassword" in element_id:
            score += 120
        if "password" in element_id:
            score += 80
        if "password" in placeholder:
            score += 70
        if "password" in name:
            score += 60
        if "current-password" in autocomplete or "password" in autocomplete:
            score += 30
        if typ in {"email", "checkbox", "hidden", "submit", "button"}:
            score -= 300

    if "background_282d44" in classes:
        score += 10

    try:
        nearby_text = driver.execute_script(
            """
            let e = arguments[0];
            let out = '';
            for (let i = 0; e && i < 5; i++, e = e.parentElement) {
                out += ' ' + (e.innerText || '');
            }
            return out.toLowerCase();
            """,
            el
        ) or ""

        if "log in" in nearby_text or "login" in nearby_text:
            score += 20

        if kind == "email" and "email" in nearby_text:
            score += 20

        if kind == "password" and "password" in nearby_text:
            score += 20

    except Exception:
        pass

    return score


def _find_best_input(driver, kind: str):
    locators = EMAIL_FIELD_LOCATORS if kind == "email" else PASSWORD_FIELD_LOCATORS

    candidates = []
    seen = set()

    for by, value in locators:
        try:
            elements = driver.find_elements(by, value)

            for el in elements:
                try:
                    remote_id = getattr(el, "id", None) or str(el)

                    if remote_id in seen:
                        continue

                    seen.add(remote_id)

                    score = _score_input_candidate(driver, el, kind)

                    if score > 0:
                        candidates.append((score, el))

                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best = candidates[0]

    print(f"[Chipnwin] Selected {kind} input candidate with score {best_score}.")
    return best


def _input_value(driver, el) -> str:
    try:
        return driver.execute_script("return arguments[0].value || '';", el) or ""
    except Exception:
        try:
            return el.get_attribute("value") or ""
        except Exception:
            return ""


def _set_input_value(driver, el, value: str, label: str) -> bool:
    _scroll_into_view(driver, el)

    try:
        el.click()
        time.sleep(0.2)
    except Exception:
        pass

    try:
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        el.send_keys(value)
        time.sleep(0.4)

        current = _input_value(driver, el)

        if current == value:
            print(f"[Chipnwin] Entered {label} with send_keys.")
            return True

        print(f"[Chipnwin] send_keys did not stick for {label}. Current length={len(current)}")

    except Exception as e:
        print(f"[Chipnwin] send_keys failed for {label}: {e}")

    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];

            el.focus();

            const proto = Object.getPrototypeOf(el);
            const descriptor =
                Object.getOwnPropertyDescriptor(proto, 'value') ||
                Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');

            if (descriptor && descriptor.set) {
                descriptor.set.call(el, value);
            } else {
                el.value = value;
            }

            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            """,
            el,
            value,
        )

        time.sleep(0.5)
        current = _input_value(driver, el)

        if current == value:
            print(f"[Chipnwin] Entered {label} with JS/native input events.")
            return True

        print(f"[Chipnwin] JS input did not stick for {label}. Current length={len(current)}")

    except Exception as e:
        print(f"[Chipnwin] JS input fallback failed for {label}: {e}")

    return False


def _find_login_submit_button(driver, password_el=None):
    candidates = []
    seen = set()

    for xp in LOGIN_SUBMIT_XPATHS:
        try:
            for btn in driver.find_elements(By.XPATH, xp):
                remote_id = getattr(btn, "id", None) or str(btn)

                if remote_id in seen:
                    continue

                seen.add(remote_id)

                if _is_visible(btn):
                    candidates.append(btn)

        except Exception:
            continue

    try:
        for btn in driver.find_elements(By.XPATH, "//button"):
            remote_id = getattr(btn, "id", None) or str(btn)

            if remote_id in seen:
                continue

            seen.add(remote_id)

            if _is_visible(btn):
                candidates.append(btn)

    except Exception:
        pass

    scored = []

    for btn in candidates:
        try:
            if not _is_enabled(btn):
                continue

            if _element_disabled_or_not_allowed(driver, btn):
                continue

            score = 0
            text = _element_text(driver, btn).lower()
            typ = _lower_attr(btn, "type")
            classes = _lower_attr(btn, "class")

            if typ == "submit":
                score += 40

            if text in {"log in", "login", "sign in", "signin"}:
                score += 100
            elif "log in" in text or "login" in text or "sign in" in text:
                score += 60

            if "primary" in classes:
                score += 10

            if password_el is not None:
                try:
                    btn_rect = btn.rect
                    pw_rect = password_el.rect

                    # Prefer the real submit below the password input,
                    # not the top tab button.
                    if btn_rect.get("y", 0) > pw_rect.get("y", 0):
                        score += 80
                    else:
                        score -= 60

                except Exception:
                    pass

            try:
                nearby_text = driver.execute_script(
                    """
                    let e = arguments[0];
                    let out = '';
                    for (let i = 0; e && i < 5; i++, e = e.parentElement) {
                        out += ' ' + (e.innerText || '');
                    }
                    return out.toLowerCase();
                    """,
                    btn
                ) or ""

                if "forgot your password" in nearby_text:
                    score += 40

                if "email" in nearby_text and "password" in nearby_text:
                    score += 40

                if "sign up" in nearby_text and "forgot" not in nearby_text:
                    score -= 20

            except Exception:
                pass

            if score > 0:
                scored.append((score, btn, text))

        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_btn, best_text = scored[0]
    print(f"[Chipnwin] Selected login submit candidate score={best_score}, text={best_text!r}.")
    return best_btn


# ───────────────────────────────────────────────────────────
# State Detection
# ───────────────────────────────────────────────────────────

def _login_form_present(driver) -> bool:
    try:
        url = (driver.current_url or "").lower()
        if "#/login" in url:
            email = _find_best_input(driver, "email")
            password = _find_best_input(driver, "password")
            if email or password:
                return True
    except Exception:
        pass

    email = _find_best_input(driver, "email")
    password = _find_best_input(driver, "password")

    return bool(email and password)


def _daily_rewards_modal_open(driver) -> bool:
    """
    This must be strict.
    Do NOT treat the login artwork text like "Daily to get free rewards" as the rewards modal.
    """
    strict_checks = [
        "//*[normalize-space()='Daily Rewards' or normalize-space()='DAILY REWARDS']",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in daily to claim prizes')]",
        "//div[contains(@class, 'daily-rewards__card')]",
    ]

    for xp in strict_checks:
        try:
            elements = driver.find_elements(By.XPATH, xp)

            for el in elements:
                if _is_visible(el):
                    return True

        except Exception:
            continue

    # Claim button alone is not enough unless nearby text says Daily Rewards.
    try:
        buttons = driver.find_elements(
            By.XPATH,
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'claim')]"
        )

        for btn in buttons:
            if not _is_visible(btn):
                continue

            nearby_text = driver.execute_script(
                """
                let e = arguments[0];
                let out = '';
                for (let i = 0; e && i < 6; i++, e = e.parentElement) {
                    out += ' ' + (e.innerText || '');
                }
                return out.toLowerCase();
                """,
                btn
            ) or ""

            if "daily rewards" in nearby_text or "log in daily to claim prizes" in nearby_text:
                return True

    except Exception:
        pass

    return False


def _is_logged_in(driver) -> bool:
    """
    Strong logged-in check only.

    This intentionally does NOT use broad text like 'store' or 'wallet'
    because those caused false positives when the login modal/page was open.
    """
    try:
        url = (driver.current_url or "").lower()

        if "#/login" in url:
            return False
    except Exception:
        pass

    if _login_form_present(driver):
        return False

    strong_checks = [
        "//span[@data-test='balance']",
        "//*[contains(@class, 'balance') and contains(normalize-space(.), '.')]",
        "//*[contains(@class, 'balance') and contains(normalize-space(.), '$')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'logout')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log out')]",
    ]

    for xp in strong_checks:
        try:
            elements = driver.find_elements(By.XPATH, xp)

            for el in elements:
                if _is_visible(el):
                    text = _element_text(driver, el)

                    # Balance can be icon-only or text-based. Visibility is enough
                    # for data-test='balance', but not for random broad xpaths.
                    if "@data-test='balance'" in xp:
                        return True

                    if text:
                        return True

        except Exception:
            continue

    return False


def _get_page_state(driver) -> str:
    if _daily_rewards_modal_open(driver):
        return "daily_rewards"

    if _login_form_present(driver):
        return "login"

    if _is_logged_in(driver):
        return "logged_in"

    try:
        url = (driver.current_url or "").lower()

        if "#/login" in url:
            return "login"

        if "store/features" in url:
            return "store"

    except Exception:
        pass

    return "unknown"


# ───────────────────────────────────────────────────────────
# Login Flow Helpers
# ───────────────────────────────────────────────────────────

async def _accept_cookies(driver):
    print("[Chipnwin] Attempting to accept cookie...")
    for cb in COOKIE_BUTTON_XPATHS:
        try:
            cookie = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, cb))
            )

            if _safe_click(driver, cookie, "cookie button"):
                await asyncio.sleep(2)
                return True

        except TimeoutException:
            pass
        except Exception:
            pass

    return False


async def _wait_for_login_form(driver, timeout=15):
    end = time.time() + timeout

    while time.time() < end:
        email = _find_best_input(driver, "email")
        password = _find_best_input(driver, "password")

        if email and password:
            return email, password

        await asyncio.sleep(1)

    return None, None


async def _wait_for_logged_in_or_rewards(driver, timeout=18) -> bool:
    end = time.time() + timeout

    while time.time() < end:
        if _daily_rewards_modal_open(driver):
            return True

        if _is_logged_in(driver):
            return True

        await asyncio.sleep(1)

    return False


async def _login_chipnwin(ctx, driver, channel, username: str, password: str) -> bool:
    print("[Chipnwin] Navigating directly to login URL...")
    driver.get(LOGIN_URL)
    await asyncio.sleep(6)

    await _accept_cookies(driver)

    if _daily_rewards_modal_open(driver) or _is_logged_in(driver):
        print("[Chipnwin] Already authenticated after loading login URL.")
        return True

    print(f"[Chipnwin] Page state before locating login fields: {_get_page_state(driver)}")

    email_el, password_el = await _wait_for_login_form(driver, timeout=15)

    if not email_el or not password_el:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] Login page opened, but email/password fields were not found.",
            "chipnwin_login_fields_not_found.png"
        )
        return False

    email_ok = _set_input_value(driver, email_el, username, "email")
    password_ok = _set_input_value(driver, password_el, password, "password")

    if not email_ok or not password_ok:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] Could not enter email/password into login form.",
            "chipnwin_login_input_failed.png"
        )
        return False

    await asyncio.sleep(1)

    submit_btn = _find_login_submit_button(driver, password_el=password_el)

    submitted = False

    if submit_btn:
        submitted = _safe_click(driver, submit_btn, "login submit button")
        await asyncio.sleep(8)

    if not submitted:
        print("[Chipnwin] Submit button click failed. Trying Enter on password field.")
        try:
            password_el.send_keys(Keys.ENTER)
            submitted = True
            await asyncio.sleep(8)
        except Exception:
            submitted = False

    if not submitted:
        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] Could not submit login form.",
            "chipnwin_login_submit_failed.png"
        )
        return False

    if await _wait_for_logged_in_or_rewards(driver, timeout=18):
        print("[Chipnwin] Login confirmed.")
        return True

    print("[Chipnwin] Login not confirmed yet. Probing rewards URL once.")
    try:
        driver.get(REWARDS_URL)
        await asyncio.sleep(8)
    except Exception:
        pass

    if _daily_rewards_modal_open(driver) or _is_logged_in(driver):
        print("[Chipnwin] Login confirmed after rewards probe.")
        return True

    await _send_screenshot(
        channel,
        driver,
        "[Chipnwin] Login submitted, but logged-in/rewards state was not confirmed.",
        "chipnwin_login_not_confirmed.png"
    )
    return False


# ───────────────────────────────────────────────────────────
# Countdown Helpers
# ───────────────────────────────────────────────────────────

def _clean_countdown(raw: str) -> str | None:
    if not raw:
        return None

    raw = raw.replace("\xa0", " ")

    match = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*:\s*(\d{2})", raw)

    if not match:
        return None

    h, m, s = match.groups()
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"


def _score_countdown_candidate(driver, el, text: str) -> int:
    score = 0

    try:
        tag = (el.tag_name or "").lower()
        if tag == "p":
            score += 20
    except Exception:
        pass

    classes = _lower_attr(el, "class")

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

    if re.fullmatch(r"\s*\d{1,2}\s*:\s*\d{2}\s*:\s*\d{2}\s*", text or ""):
        score += 40
    elif _clean_countdown(text):
        score += 10

    return score


def _read_countdown(driver, timeout=8) -> str | None:
    candidates = []
    seen = set()
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

                        if not _is_visible(el):
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

        time.sleep(2)

    return None


# ───────────────────────────────────────────────────────────
# Rewards Flow
# ───────────────────────────────────────────────────────────

async def _open_daily_rewards(driver):
    print("[Chipnwin] Navigating directly to rewards page...")
    driver.get(REWARDS_URL)
    await asyncio.sleep(8)

    if _daily_rewards_modal_open(driver):
        print("[Chipnwin] Daily Rewards modal/page opened from direct link.")
        return True

    state = _get_page_state(driver)
    print(f"[Chipnwin] State after rewards URL: {state}")

    if state == "login":
        return False

    print("[Chipnwin] Direct rewards route did not open modal. Trying store card...")
    driver.get(STORE_URL)
    await asyncio.sleep(6)

    if _login_form_present(driver):
        print("[Chipnwin] Login form appeared while trying store.")
        return False

    _, start_btn = _first_clickable(driver, START_BUTTON_XPATHS, timeout=8)

    if start_btn:
        if _safe_click(driver, start_btn, "daily rewards card"):
            await asyncio.sleep(5)

            if _daily_rewards_modal_open(driver):
                print("[Chipnwin] Daily Rewards modal opened from card.")
                return True

    print("[Chipnwin] Could not confirm Daily Rewards modal/page is open.")
    return False


def _find_claim_button(driver, timeout=8):
    for xp in CLAIM_BUTTON_XPATHS:
        try:
            btn = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )

            if not _is_visible(btn):
                continue

            text = _element_text(driver, btn).lower()

            if "claim" not in text:
                continue

            return xp, btn

        except TimeoutException:
            continue
        except Exception:
            continue

    return None, None


def _confirm_claim_succeeded(driver, clicked_element, timeout=8) -> bool:
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
                if _is_visible(el):
                    return True

        except Exception:
            continue

    return False


# ───────────────────────────────────────────────────────────
# Main Casino Flow
# ───────────────────────────────────────────────────────────

async def chipnwin_casino(ctx, driver, channel):
    if not CHIPNWIN_CRED:
        await channel.send("❌ Missing `CHIPNWIN` as 'email:password' in your .env.")
        return

    username, password = CHIPNWIN_CRED.split(":", 1)

    print("[Chipnwin] Starting flow...")

    # First probe direct rewards. If it opens, we are truly logged in.
    try:
        driver.get(REWARDS_URL)
        await asyncio.sleep(8)
        await _accept_cookies(driver)
    except Exception:
        pass

    if _daily_rewards_modal_open(driver):
        print("[Chipnwin] Rewards opened immediately. User is logged in.")
        await claim_chipnwin_bonus(ctx, driver, channel, already_open=True)
        return

    # If rewards did not open, do NOT trust broad logged-in checks.
    # Go straight to direct login.
    print(f"[Chipnwin] Rewards did not open. Current state: {_get_page_state(driver)}")
    print("[Chipnwin] Logging in through direct login URL.")

    ok = await _login_chipnwin(ctx, driver, channel, username, password)

    if not ok:
        return

    await claim_chipnwin_bonus(ctx, driver, channel)


async def claim_chipnwin_bonus(ctx, driver, channel, already_open: bool = False):
    print("[Chipnwin] Opening Daily Rewards...")

    opened = already_open

    if not opened:
        opened = await _open_daily_rewards(driver)

    if not opened:
        # It may have failed because login expired.
        state = _get_page_state(driver)

        if state == "login":
            await _send_screenshot(
                channel,
                driver,
                "[Chipnwin] Daily Rewards did not open because login is required.",
                "chipnwin_rewards_needs_login.png"
            )
            return

        await _send_screenshot(
            channel,
            driver,
            "[Chipnwin] Could not open Daily Rewards page/modal.",
            "chipnwin_rewards_open_error.png"
        )
        return

    print(f"[Chipnwin] State inside claim flow: {_get_page_state(driver)}")

    # Read countdown first to avoid false-positive claims.
    print("[Chipnwin] Searching for Daily Rewards countdown candidate before claiming...")
    countdown = _read_countdown(driver, timeout=10)

    if countdown:
        await _send_countdown(channel, countdown)
        return

    print("[Chipnwin] No countdown found. Looking for claim button...")
    claim_xpath, claim_btn = _find_claim_button(driver, timeout=6)

    if claim_btn:
        claim_text = _element_text(driver, claim_btn)
        print(f"[Chipnwin] Claim candidate text: {claim_text!r}")

        if _element_disabled_or_not_allowed(driver, claim_btn):
            print("[Chipnwin] Claim button disabled/not allowed. Reading countdown again.")
            countdown = _read_countdown(driver, timeout=8)

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
                await _send_screenshot(
                    channel,
                    driver,
                    "Chipnwin Daily Bonus Claimed!",
                    "chipnwin_claim.png"
                )
                return

            print("[Chipnwin] Claim click did not confirm. Checking countdown.")

    print("[Chipnwin] Searching for Daily Rewards countdown candidate after claim attempt...")
    countdown = _read_countdown(driver, timeout=12)

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
# Standalone Countdown Reader
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
# Daily Spin Wheel
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