# Drake Hooks + WaterTrooper
# Casino Claim 3
# Jolly Sweeps API
# Version 3.4
# Updated 2026.08.06

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
JOLLYSWEEPS_CRED = os.getenv("JOLLYSWEEPS")  # format "username:password"

SITE_URL = "https://jollysweeps.com"
LOGIN_URL = "https://jollysweeps.com/login"
LOBBY_URL = "https://jollysweeps.com/home"
PROMOTIONS_URL = "https://jollysweeps.com/promotions"

LOGIN_BUTTON_XPATH = "//button[contains(@class, 'inline-flex items-center justify-center gap-2 outline-none')]//span[text()='Login']"
EMAIL_INPUT_XPATH = "//input[@name='login']"
PASSWORD_INPUT_XPATH = "//input[@name='password']"
LOGIN_SUBMIT_XPATH = "//button[contains(@class, 'inline-flex items-center justify-center gap-2 outline-none') and text()='Continue']"

REWARD_BUTTON_XPATH = "//button[contains(@class, 'inline-flex items-center justify-center gap-2 outline-none')]//span[text()='Claim Daily Reward']"
CLAIM_BUTTON_XPATH = "//button[contains(@class, 'inline-flex items-center justify-center gap-2 outline-none') and text()='Confirm Claim']"


# ───────────────────────────────────────────────────────────
# 0) Helpers
# ───────────────────────────────────────────────────────────

def _is_logged_in(driver) -> bool:
    """Detect if already logged in."""
    try:
        driver.find_element(By.XPATH, "//span[@class='text-muted-foreground font-semibold text-sm' and text()='GC']")
        return True
    except NoSuchElementException:
        pass
    try:
        driver.find_element(By.XPATH, "//span[@class='text-muted-foreground font-semibold text-sm' and text()='SC']")
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
        print(f"[Jolly Sweeps] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[Jolly Sweeps] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[Jolly Sweeps] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[Jolly Sweeps] JS click failed for {label}: {e}")

    return False


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[Jolly Sweeps] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def jollysweeps_casino(ctx, driver, channel):
    if not JOLLYSWEEPS_CRED:
        await channel.send("❌ Missing `JOLLYSWEEPS` as 'email:password' in your .env.")
        return

    username, password = JOLLYSWEEPS_CRED.split(":", 1)

    print("[Jolly Sweeps] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)

    if _is_logged_in(driver):
        print("[Jolly Sweeps] Already logged in.")
        await claim_jollysweeps_bonus(ctx, driver, channel)
        return

    print("[Jolly Sweeps] Attempting to login...")
    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Jolly Sweeps] Login button failed: {e}")

            try:
                print("[Jolly Sweeps] Trying direct signin URL...")
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
            print(f"[Jolly Sweeps] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Jolly Sweeps] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "login submit button")
            print("[Jolly Sweeps] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[Jolly Sweeps] Submit failed: {e}")

        await claim_jollysweeps_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print(f"[Jolly Sweeps] Login timeout: {e}")

        await _send_screenshot(
            channel,
            driver,
            "Jolly Sweeps login timed out.",
            "jollysweeps_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_jollysweeps_bonus(ctx, driver, channel):

    print("[Jolly Sweeps] Navigating to promotions...")
    try:
        driver.get(PROMOTIONS_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Jolly Sweeps] Promotions navigation error: {e}")

    print ("[Jolly Sweeps] Attempting to click reward button...")
    try:
        reward = _wait_clickable(driver, By.XPATH, REWARD_BUTTON_XPATH, timeout=10)
        _safe_click(driver, reward, "reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[Jolly Sweeps] Reward failed: {e}")

    print("[Jolly Sweeps] Attempting to claim daily bonus...")
    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        _safe_click(driver, claim, "claim button")

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "jollysweeps_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("Jolly Sweeps Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[Jolly Sweeps] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "jollysweeps_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("Jolly Sweeps Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)         