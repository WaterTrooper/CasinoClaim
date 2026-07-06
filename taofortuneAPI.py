# Drake Hooks + WaterTrooper
# Casino Claim 3.4
# TaoFortune API
# Version 3.4
# Updated 2026.07.02

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
TAOFORTUNE_CRED = os.getenv("TAOFORTUNE")  # format "username:password"

SITE_URL = "https://taofortune.com"
LOGIN_URL = "https://taofortune.com/signin"
LOBBY_URL = "https://taofortune.com/lobby"
PROMOTIONS_URL = "https://taofortune.com/promotions"

LOGIN_BUTTON_XPATH = "//button[@data-tid='header-login-btn']"
EMAIL_INPUT_XPATH = "//input[@data-tid='login-email-input']"
PASSWORD_INPUT_XPATH = "//input[@data-tid='login-password-input']"
LOGIN_SUBMIT_XPATH = "//button[@data-tid='login-btn']"

POPUP_BUTTON_XPATH = "//span[@data-tid='close-modal']"
REWARD_BUTTON_XPATH = "//button[@data-tid='promo-daily-rewards-button']"
CLAIM_BUTTON_XPATH = "//button[@data-tid='dailyRewards_modal_play_collect']"


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
        print(f"[TaoFortune] Clicked {label}.")
        return True
    except Exception as e:
        print(f"[TaoFortune] Normal click failed for {label}: {e}")

    try:
        driver.execute_script("arguments[0].click();", element)
        print(f"[TaoFortune] JS clicked {label}.")
        return True
    except Exception as e:
        print(f"[TaoFortune] JS click failed for {label}: {e}")

    return False


async def _send_screenshot(channel, driver, message, filename):
    try:
        driver.save_screenshot(filename)

        await channel.send(
            message,
            file=discord.File(filename)
        )

    except Exception as e:
        print(f"[TaoFortune] Screenshot send failed: {e}")
        await channel.send(message)

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass   


# ───────────────────────────────────────────────────────────
# 1) Login Flow
# ───────────────────────────────────────────────────────────

async def taofortune_casino(ctx, driver, channel):
    if not TAOFORTUNE_CRED:
        await channel.send("❌ Missing `TAOFORTUNE` as 'email:password' in your .env.")
        return

    username, password = TAOFORTUNE_CRED.split(":", 1)

    print("[TaoFortune] Navigating to site...")
    driver.get(SITE_URL)
    await asyncio.sleep(10)  

    if _is_logged_in(driver):
        print("[TaoFortune] Already logged in.")
        await claim_taofortune_bonus(ctx, driver, channel)
        return

    print("[TaoFortune] Attempting to login...")
    try:
        try:
            login = _wait_clickable(driver, By.XPATH, LOGIN_BUTTON_XPATH, timeout=10)
            _safe_click(driver, login, "login button")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[TaoFortune] Login button failed: {e}")

            try:
                print("[TaoFortune] Trying direct signin URL...")
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
            print(f"[TaoFortune] Email input failed: {e}")

        try:
            pw = _wait_present(driver, By.XPATH, PASSWORD_INPUT_XPATH, timeout=10)
            pw.clear()
            pw.send_keys(password)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[TaoFortune] Password input failed: {e}")

        try:
            submit = _wait_clickable(driver, By.XPATH, LOGIN_SUBMIT_XPATH, timeout=10)
            _safe_click(driver, submit, "login submit button")
            print("[TaoFortune] Submitted credentials.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[TaoFortune] Submit failed: {e}")                    

        await claim_taofortune_bonus(ctx, driver, channel)

    except TimeoutException as e:
        print(f"[TaoFortune] Login timeout: {e}")

        await _send_screenshot(
            channel,
            driver,
            "TaoFortune login timed out.",
            "taofortune_login_error.png"
        )


# ───────────────────────────────────────────────────────────
# 2) Claim Bonus
# ───────────────────────────────────────────────────────────

async def claim_taofortune_bonus(ctx, driver, channel):
    print("[TaoFortune] Navigating to promotions...")

    try:
        driver.get(PROMOTIONS_URL)
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[TaoFortune] Promotions navigation error: {e}")

    try:
        popup = _wait_clickable(driver, By.XPATH, POPUP_BUTTON_XPATH, timeout=10)
        _safe_click(driver, popup, "popup button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[TaoFortune] Popup failed: {e}")          

    try:
        reward = _wait_clickable(driver, By.XPATH, REWARD_BUTTON_XPATH, timeout=10)
        _safe_click(driver, reward, "reward button")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[TaoFortune] Reward failed: {e}")             

    print("[TaoFortune] Attempting to claim daily bonus...")
    try:
        claim = _wait_clickable(driver, By.XPATH, CLAIM_BUTTON_XPATH, timeout=10)
        _safe_click(driver, claim, "claim button")

        await asyncio.sleep(5)

        # 📸 success screenshot
        screenshot = "taofortune_claim.png"
        driver.save_screenshot(screenshot)

        await channel.send("TaoFortune Daily Bonus Claimed!",file=discord.File(screenshot))

        os.remove(screenshot)

    except Exception as e:
        print(f"[TaoFortune] Claim failed: {e}")

        # 📸 error screenshot
        screenshot = "taofortune_claim_error.png"
        driver.save_screenshot(screenshot)

        await channel.send("TaoFortune Daily Bonus Unavailable.",file=discord.File(screenshot))

        os.remove(screenshot)                     