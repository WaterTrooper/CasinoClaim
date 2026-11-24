# Drake Hooks + WaterTrooper
# Casino Claim 3
# BigHit API
# Version 4
# Updated 2026.11.24

import os
import asyncio
import discord
import contextlib
from pathlib import Path
from dotenv import load_dotenv
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


# ───────────────────────────────────────────────────────────
# Config & Constants
# ───────────────────────────────────────────────────────────


load_dotenv()
BIGHIT_CRED = os.getenv("BIGHIT")  # format "username:password"

SITE_URL = "https://bighit.us"

LOGIN_BUTTON_XPATH = "//button[contains(@class,'MuiButtonBase-root MuiButton-root MuiButton-contained') and text()='Login']"
EMAIL_INPUT_XPATH = "email"
PASSWORD_INPUT_XPATH = "password"
SUBMIT_LOGIN_XPATH = "//button[contains(@class,'MuiButtonBase-root MuiButton-root MuiButton-contained') and text()='Log in']"

REWARD_BUTTON_XPATH = "//button[@aria-label='GC daily bonus widget']"
CLAIM_BUTTON_XPATH = "//button[contains(@class,'MuiButton-containedPrimary') and contains(text(),'laim')]"


# ───────────────────────────────────────────────────────────
# Main Flow
# ───────────────────────────────────────────────────────────


async def bighit_uc(ctx, channel: discord.abc.Messageable):

    await channel.send("Launching **BigHit** (UC)...")

    if not BIGHIT_CRED:
        await channel.send("❌ Missing `BIGHIT` as 'email:password' in your .env.")
        return

    username, password = BIGHIT_CRED.split(":", 1)

    try:
        with SB(uc=True, headed=True) as sb:

            print("[BigHit] Navigating to site...")
            try:
                sb.maximize()
                sb.wait(10)
                sb.uc_open_with_reconnect(SITE_URL, 4)
                sb.wait_for_ready_state_complete()
                print("[BigHit] Site loaded.")
            except Exception as e:
                print(f"[BigHit] Site navigation error: {e}")

            print("[BigHit] Attempting to login...")
            try:
                sb.click(LOGIN_BUTTON_XPATH)
                sb.wait(10)
            except Exception as e:
                print(f"[BigHit] Login button failed: {e}")

            try:
                sb.type(f"input[name='{EMAIL_INPUT_XPATH}']", username)
                sb.wait(5)
            except Exception as e:
                print(f"[BigHit] Email input failed: {e}")

            try:
                sb.type(f"input[name='{PASSWORD_INPUT_XPATH}']", password)
                sb.wait(5)
            except Exception as e:
                print(f"[BigHit] Password input failed: {e}")

            try:
                sb.click(SUBMIT_LOGIN_XPATH)
                print("[BigHit] Submitted credentials.")
                sb.wait(10)
            except Exception as e:
                print(f"[BigHit] Submit login failed: {e}")

            print("[Bighit] Attempting to click reward button...")
            try:
                sb.click(REWARD_BUTTON_XPATH)
                sb.wait(10)
            except Exception as e:
                print(f"[BigHit] Reward button failed: {e}")

            print("[BigHit] Attempting to claim daily bonus...")
            try:
                sb.click(CLAIM_BUTTON_XPATH)
                #sb.click('button.MuiButton-containedPrimary:contains("laim")')
                sb.wait(5)
                screenshot = "bighit_claim.png"
                sb.save_screenshot(screenshot)

                await channel.send("BigHit Daily Bonus Claimed!",file=discord.File(screenshot))

                os.remove(screenshot)

            except Exception as e:
                print(f"[BigHit] Claim failed: {e}")
                screenshot = "bighit_claim_error.png"
                sb.save_screenshot(screenshot)

                await channel.send("BigHit Daily Bonus Unavailable.",file=discord.File(screenshot))

                os.remove(screenshot)
    except Exception as e:
        print(f"[BigHit][ERROR] Exception during automation: {e}")    