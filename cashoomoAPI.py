# Drake Hooks + WaterTrooper
# Casino Claim 3
# Cashoomo API
# Version 3.3
# Updated: 2026.06.17

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
from selenium.webdriver.common.action_chains import ActionChains

# ───────────────────────────────────────────────────────────
# Config & Constants
# ───────────────────────────────────────────────────────────

load_dotenv()
CASHOOMO_CRED = os.getenv("CASHOOMO")  # format "username:password"

SITE_URL = "https://cashoomo.com"
MAIN_URL = "https://cashoomo.com/main"

LOGIN_BUTTON_XPATH = "//div[@class='btn-secondary size-lg']"
EMAIL_INPUT_XPATH = "//input[@type='email']"
PASSWORD_INPUT_XPATH = "//input[@type='password']"
LOGIN_SUBMIT_XPATH = "//div[@data-event_name='Submit Login']"

REWARD_WIDGET_XPATH = "//div[@class='widget widget__daily-reward']"
CLAIM_BUTTON_XPATH = "//div[contains(@class, 'modal-daily-bonus-claim__button')]"

# ───────────────────────────────────────────────────────────
# 0) Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//div[@class='coins__toggler']")
        return True
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//button[@class='btn-deposit']")
        return True
    except NoSuchElementException:
        return False

# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def cashoomo_casino(ctx, driver, channel):
    if not CASHOOMO_CRED:
        await channel.send("❌ Missing `CASHOOMO` as 'email:password' in your .env.")
        return

    username, password = CASHOOMO_CRED.split(":", 1)

    print("[Cashoomo] Navigating to site...")
    try:
        driver.get(SITE_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"Error: {e}")

    if _is_logged_in(driver):
        print("[Cashoomo] Already logged in.")
        await claim_cashoomo_bonus(ctx, driver, channel)
        return

    print("[Cashoomo] Attempting to login...")
    try:
        try:
            login = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, LOGIN_BUTTON_XPATH)))
            login.click()
            await asyncio.sleep(10)
        except Exception:
            print("[Cashoomo] Login button failed.")

        try:
            email = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, EMAIL_INPUT_XPATH)))
            email.send_keys(username)
            await asyncio.sleep(5)
        except Exception:
            print("[Cashoomo] Email input failed.")

        try:
            pw = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, PASSWORD_INPUT_XPATH)))
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception:
            print("[Cashoomo] Password input failed.")

        try:
            submit = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, LOGIN_SUBMIT_XPATH)))
            submit.click()
            print("[Cashoomo] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception:
            print("[Cashoomo] Submit failed.")

        await claim_cashoomo_bonus(ctx, driver, channel)

    except TimeoutException as e:
        screenshot = "cashoomo_login_error.png"
        driver.save_screenshot(screenshot)
        await channel.send("Cashoomo login timed out.",file=discord.File(screenshot))
        os.remove(screenshot)
        print(f"Login timeout: {e}")

# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_cashoomo_bonus(ctx, driver, channel):

    print("[Cashoomo] Navigating to main...")
    try:
        driver.get(MAIN_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"Error: {e}")

    print("[Cashoomo] Attempting to click widget...")
    try:
        widget = WebDriverWait(driver, 10).until((EC.element_to_be_clickable((By.XPATH, REWARD_WIDGET_XPATH))))
        widget.click()
        await asyncio.sleep(10)
    except Exception:
        print("[Cashoomo] Widget failed.")        

    print("[Cashoomo] Attempting to claim daily bonus...")
    try:
        claim = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, CLAIM_BUTTON_XPATH)))
        # normal click
        try:
            claim.click()
        except Exception:
            # fallback JS click (very important for these sites)
            driver.execute_script("arguments[0].click();", claim)

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "cashoomo_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("Cashoomo Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[Cashoomo] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "cashoomo_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("Cashoomo Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)         