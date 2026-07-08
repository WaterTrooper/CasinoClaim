# Drake Hooks + WaterTrooper
# Casino Claim 3
# Zumo API
# Version 3.4
# Updated 2026.07.07

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
ZUMO_CRED = os.getenv("ZUMO")  # format "username:password"

SITE_URL = "https://zumo.us"

LOGIN_BUTTON_XPATH = "//button[contains(@class, 'bg-gray-900 text-gray-0 border-gray-900')]"
EMAIL_INPUT_XPATH = "//input[@name='email']"
PASSWORD_INPUT_XPATH = "//input[@name='password']"
LOGIN_SUBMIT_XPATH = "//button[contains(@class, 'border-orange-100 bg-orange-300')]//span[text()='Log In']"

POPUP_BUTTON_XPATH = "//button[@class='group flex cursor-pointer items-center justify-center absolute right-xs mb-3xs']"
REWARD_BUTTON_XPATH = "//span[contains(@class, 'font-bold whitespace-nowrap text-gray-1000') and contains(text(), 'Claim')]"
CLAIM_BUTTON_XPATH = "//button[contains(@class, 'text-black border-green-100 bg-green-300')]//span[text()='Claim']"


# ───────────────────────────────────────────────────────────
# 0) Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//div[@class='absolute inset-[3px] rounded-full bg-gray-800']")
        return True
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//button[@class='group cursor-pointer hidden size-xl items-center justify-center rounded-full border border-blue-100 md:flex']")
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
        print(f"[Zumo] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[Zumo] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[Zumo] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[Zumo] JS click failed for {label}: {e}")

    return False


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[Zumo] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass   


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def zumo_casino(ctx, driver, channel):
    if not ZUMO_CRED:
        await channel.send("❌ Missing `ZUMO` as 'email:password' in your .env.")
        return

    username, password = ZUMO_CRED.split(":", 1)

    print("[Zumo] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)  

    if _is_logged_in(driver):
        print("[Zumo] Already logged in.")
        await claim_zumo_bonus(ctx, driver, channel)
        return

    print("[Zumo] Attempting to login...")
    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Zumo] Login button failed: {e}")

        try:
            email = _wait_present(driver, By.XPATH, EMAIL_INPUT_XPATH, timeout=10)
            email.clear()
            email.send_keys(username)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Zumo] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Zumo] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "login submit button")
            print("[Zumo] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Zumo] Submit failed: {e}")

        await claim_zumo_bonus(ctx, driver, channel)            

    except TimeoutException as e:
        print(f"[Zumo] Login timeout: {e}")

        await _send_screenshot(
            channel,
            driver,
            "Zumo login timed out.",
            "zumo_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_zumo_bonus(ctx, driver, channel):      

    print("[Zumo] Attemping to close zumo shop modal...")
    try:
        popup = _wait_clickable(driver, By.XPATH, POPUP_BUTTON_XPATH, timeout=10)
        _safe_click(driver, popup, "popup button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Zumo] Popup failed: {e}")

    print("[Zumo] Attempting to click on reward button...")
    try:
        reward = _wait_clickable(driver, By.XPATH, REWARD_BUTTON_XPATH, timeout=10)
        _safe_click(driver, reward, "reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Zumo] Reward failed: {e}")                  

    print("[Zumo] Attempting to claim daily bonus...")
    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        _safe_click(driver, claim, "claim button")

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "zumo_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("Zumo Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[Zumo] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "zumo_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("Zumo Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)                           