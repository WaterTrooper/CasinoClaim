# Drake Hooks + WaterTrooper
# Casino Claim 3
# Rollza API
# Version 3.4
# Updated 2026.11.27

import re
import os
import asyncio
import discord
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


# ───────────────────────────────────────────────────────────
# Config & Constants
# ───────────────────────────────────────────────────────────


load_dotenv()
ROLLZA_CRED = os.getenv("ROLLZA")  # format "username:password"

SITE_URL = "https://rollza.com"
LOBBY_URL = "https://rollza.com/home"
REWARDS_URL = "https://rollza.com/rewards"

LOGIN_BUTTON_XPATH = "//button[@type='button' and normalize-space(.)='Login']"
EMAIL_INPUT_XPATH = "//input[@name='username']"
PASSWORD_INPUT_XPATH = "//input[@name='password']"
LOGIN_SUBMIT_XPATH = "//button[@type='submit' and normalize-space()='Log In']"

BONUS_MODAL_XPATH = "//button[@aria-label='Close daily login bonus']"
REWARD_BUTTON_XPATH = "//button[@type='button' and normalize-space(.)='Claim']"
CLAIM_BUTTON_XPATH = "//button[@type='button' and normalize-space()='Claim Reward']"


# ───────────────────────────────────────────────────────────
# 0) Helpers
# ───────────────────────────────────────────────────────────


def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//button[@aria-label='Selected coin: GC']")
        return True
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//button[@aria-label='Selected coin: SC']")
        return True
    except NoSuchElementException:
        return False


def _wait_clickable(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


def _wait_present(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


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
        print(f"[Rollza] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[Rollza] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[Rollza] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[Rollza] JS click failed for {label}: {e}")

    return False


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[Rollza] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────


async def rollza_casino(ctx, driver, channel):
    if not ROLLZA_CRED:
        await channel.send("❌ Missing `ROLLZA` as 'username:password' in your .env.")
        return

    username, password = ROLLZA_CRED.split(":", 1)

    print("[Rollza] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)

    if _is_logged_in(driver):
        print("[Rollza] Already logged in.")
        await claim_rollza_bonus(ctx, driver, channel)
        return

    print("[Rollza] Attempting to login...")
    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Rollza] Login button failed: {e}")

        try:
            email = _wait_present(driver, By.XPATH, EMAIL_INPUT_XPATH, timeout=10)
            email.clear()
            email.send_keys(username)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Rollza] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Rollza] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "submit button")
            print("[Rollza] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Rollza] Submit failed: {e}")

        await claim_rollza_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print(f"[Rollza] Login timeout: {e}")

        await _send_screenshot(
            channel,
            driver,
            "Rollza login timed out.",
            "rollza_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────


async def claim_rollza_bonus(ctx, driver, channel):

    print ("[Rollza] Attempting to close bonus modal")
    try:
        bonus = _wait_clickable(driver, By.XPATH, BONUS_MODAL_XPATH, timeout=10)
        _safe_click(driver, bonus, "bonus modal close button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Rollza] Bonus failed: {e}")

    print("[Rollza] Navigating to rewards...")
    try:
        driver.get(REWARDS_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Rollza] Rewards navigation error: {e}")

    print ("[Rollza] Attempting to click reward button")
    try:
        reward = _wait_clickable(driver, By.XPATH, REWARD_BUTTON_XPATH, timeout=10)
        _safe_click(driver, reward, "reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Rollza] Reward failed: {e}")

    print("[Rollza] Attempting to claim daily bonus...")
    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        _safe_click(driver, claim, "claim button")

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "rollza_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("Rollza Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[Rollza] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "rollza_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("Rollza Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)    