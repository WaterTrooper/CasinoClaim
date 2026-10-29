# Drake Hooks + WaterTrooper
# Casino Claim 3
# VegasWay API
# Version 3.4
# Updated 2026.10.29

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
VEGASWAY_CRED = os.getenv("VEGASWAY")  # format "username:password"

SITE_URL = "https://vegasway.com"
LOGIN_URL = "https://vegasway.com/signin"
LOBBY_URL = "https://vegasway.com/lobby"
PROMOTIONS_URL = "https://vegasway.com/promotions"

LOGIN_BUTTON_XPATH = "//button[@data-tid='header-login-btn']"
EMAIL_INPUT_XPATH = "//input[@data-tid='login-email-input']"
PASSWORD_INPUT_XPATH = "//input[@data-tid='login-password-input']"
LOGIN_SUBMIT_XPATH = "//button[@data-tid='login-btn']"

MODAL_CLOSE_XPATH = "//span[@data-tid='close-modal']"
REWARD_BUTTON_XPATH = "//button[@data-tid='promo-daily-login-button']"
CLAIM_BUTTON_XPATH = "//button[@data-tid='daily-login-claim-button']"


# ───────────────────────────────────────────────────────────
# 0) Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//div[@data-tid='header-balances']")
        return True
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//button[@data-tid='header-buy-btn']")
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
        print(f"[VegasWay] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[VegasWay] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[VegasWay] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[VegasWay] JS click failed for {label}: {e}")

    return False


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[VegasWay] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def vegasway_casino(ctx, driver, channel):
    if not VEGASWAY_CRED:
        await channel.send("❌ Missing `VEGASWAY` as 'email:password' in your .env.")
        return

    username, password = VEGASWAY_CRED.split(":", 1)

    print("[VegasWay] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)

    if _is_logged_in(driver):
        print("[VegasWay] Already logged in.")
        await claim_vegasway_bonus(ctx, driver, channel)
        return        

    print("[VegasWay] Attempting to login...")
    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[VegasWay] Login button failed: {e}")

            try:
                print("[VegasWay] Trying direct signin URL...")
                driver.get(LOGIN_URL)
                await asyncio.sleep(10)
            except Exception:
                pass

        try:
            email = _wait_present(driver, By.XPATH, EMAIL_INPUT_XPATH, timeout=10)
            email.clear()
            email.send_keys(username)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[VegasWay] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[VegasWay] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "login submit button")
            print("[VegasWay] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[VegasWay] Submit failed: {e}")

        await claim_vegasway_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print(f"[VegasWay] Login timeout: {e}")

        await _send_screenshot(
            channel,
            driver,
            "VegasWay login timed out.",
            "vegasway_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_vegasway_bonus(ctx, driver, channel):

    print("[VegasWay] Navigating to promotions...")
    try:
        driver.get(PROMOTIONS_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[VegasWay] Promotions navigation error: {e}")

    print ("[VegasWay] Attempting to close modal")
    try:
        modal = _wait_clickable(driver, By.XPATH, MODAL_CLOSE_XPATH, timeout=10)
        _safe_click(driver, modal, "modal")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[VegasWay] Modal failed: {e}")

    print ("[VegasWay] Attempting to click reward button")
    try:
        reward = _wait_clickable(driver, By.XPATH, REWARD_BUTTON_XPATH, timeout=10)
        _safe_click(driver, reward, "reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[VegasWay] Reward failed: {e}")

    print("[VegasWay] Attempting to claim daily bonus...")
    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        _safe_click(driver, claim, "claim button")

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "vegasway_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("VegasWay Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[VegasWay] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "vegasway_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("VegasWay Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)