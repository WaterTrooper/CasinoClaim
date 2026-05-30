# Drake Hooks + WaterTrooper
# Casino Claim 2
# American Luck API (SeleniumBase UC)
# Notes:
# - Login flow kept intact.
# - Updated Collect logic with:
#   1. New CSS selector
#   2. Copied XPath support
#   3. Candidacy scoring system
#   4. Predictive XPath fallback system
#   5. Text scan for Collect-containing elements

import os
import discord
from dotenv import load_dotenv
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException


# ───────────────────────────────────────────────────────────
# American Luck Config and Constants
# ───────────────────────────────────────────────────────────

load_dotenv()

LOGIN_URL = "https://americanluck.com/login"
LOBBY_URL = "https://americanluck.com/lobby"

POPUP_CLOSE_XP = "/html/body/div[5]/div/button"
GET_COINS_BTN_XP = "/html/body/div[1]/div[2]/header/div[2]/button[1]"

# New inspected XPath from DevTools.
# The copied XPath points to the inner div.button-content, so code will climb
# to the parent button before clicking.
INSPECTED_COLLECT_TEXT_XP = "/html/body/div[7]/div/div/section[3]/div/div/div[1]/div/div[3]/button[1]/div[1]"
INSPECTED_COLLECT_BUTTON_XP = "/html/body/div[7]/div/div/section[3]/div/div/div[1]/div/div[3]/button[1]"

# Updated CSS selector based on the current inspected DOM:
# <div class="button-content">Collect</div>
COLLECT_BTN_CSS = (
    "div.dialog-container "
    "div.free-coin-dialog "
    "div.free-reward-card__button-container "
    "button.rag-button.rag-button--primary.free-reward-card__button"
)

COLLECT_BTN_TEXT_CSS = (
    "div.dialog-container "
    "div.free-coin-dialog "
    "div.free-reward-card__button-container "
    "button.rag-button.rag-button--primary.free-reward-card__button "
    "div.button-content"
)

# Broader CSS candidates for layout drift.
COLLECT_CSS_CANDIDATES = [
    COLLECT_BTN_CSS,
    COLLECT_BTN_TEXT_CSS,
    "div.dialog-container button.free-reward-card__button",
    "div.dialog-container .free-reward-card__button-container button",
    ".free-coin-dialog button.free-reward-card__button",
    ".free-coin-dialog .free-reward-card__button-container button",
    "button[data-sentry-component='RagButton'].free-reward-card__button",
    "button.rag-button--primary.free-reward-card__button",
    "button.free-reward-card__button",
]

# XPath candidates that search by text instead of fragile structure.
COLLECT_XPATH_CANDIDATES = [
    INSPECTED_COLLECT_BUTTON_XP,
    INSPECTED_COLLECT_TEXT_XP,

    # Button itself contains Collect.
    (
        "//div[contains(@class,'dialog-container')]"
        "//button[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect')]"
    ),

    # Child div contains Collect, then climb to button.
    (
        "//div[contains(@class,'dialog-container')]"
        "//*[contains(@class,'button-content') and "
        "contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect')]"
        "/ancestor::button[1]"
    ),

    # Free reward card button with Collect anywhere inside.
    (
        "//div[contains(@class,'free-reward-card')]"
        "//button[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect')]"
    ),

    # Any clickable-looking element that contains Collect.
    (
        "//*[self::button or @role='button' or contains(@class,'button')]"
        "[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect')]"
    ),
]

CLAIMED_TEXT_MARKERS = [
    "today's bonus is claimed",
    "todays bonus is claimed",
    "bonus is claimed",
    "already claimed",
    "claimed",
]

PURCHASE_TEXT_MARKERS = [
    "checkout",
    "buy $",
    "purchase",
    "store packs",
]


# ───────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────

async def _send_shot(sb: SB, channel: discord.abc.Messageable, path: str, caption: str):
    """Save a screenshot, send it to Discord, then clean it up."""
    try:
        sb.save_screenshot(path)
        await channel.send(caption, file=discord.File(path))
    except Exception:
        try:
            await channel.send(caption)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _safe_element_text(sb: SB, el) -> str:
    try:
        text = el.text
        if text:
            return text
    except Exception:
        pass

    try:
        return sb.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", el) or ""
    except Exception:
        return ""


def _page_text(sb: SB) -> str:
    try:
        return sb.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        try:
            return sb.get_text("body")
        except Exception:
            return ""


def _is_visible_enabled(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _find_elements_css(sb: SB, css: str):
    try:
        return sb.driver.find_elements(By.CSS_SELECTOR, css)
    except Exception:
        return []


def _find_elements_xpath(sb: SB, xpath: str):
    try:
        return sb.driver.find_elements(By.XPATH, xpath)
    except Exception:
        return []


def _button_from_element(el):
    """
    If DevTools copied the inner <div class='button-content'>Collect</div>,
    climb to the nearest parent button.
    """
    try:
        tag = (el.tag_name or "").lower()
        if tag == "button":
            return el
    except Exception:
        return el

    try:
        return el.find_element(By.XPATH, "./ancestor::button[1]")
    except Exception:
        return el


def _closest_reward_card_text(sb: SB, el) -> str:
    """
    Pull surrounding card text so the scorer can prefer Daily Bonus over
    other Collect buttons like Google Grab.
    """
    try:
        card = el.find_element(
            By.XPATH,
            "./ancestor::*[contains(@class,'free-reward-card')][1]"
        )
        return _safe_element_text(sb, card)
    except Exception:
        pass

    try:
        parent = el.find_element(By.XPATH, "./ancestor::div[1]")
        return _safe_element_text(sb, parent)
    except Exception:
        return _safe_element_text(sb, el)


def _is_probably_disabled(sb: SB, el) -> bool:
    try:
        disabled = el.get_attribute("disabled")
        aria_disabled = el.get_attribute("aria-disabled")
        classes = _norm(el.get_attribute("class") or "")

        if disabled is not None:
            return True
        if aria_disabled == "true":
            return True
        if "disabled" in classes:
            return True
    except Exception:
        pass

    return False


def _score_collect_candidate(sb: SB, el) -> int:
    """
    Higher score = better candidate.

    We want:
    - visible enabled button
    - actual Collect text
    - Daily Bonus card preferred
    - avoid More Coins / Buy / Checkout / purchase buttons
    """
    try:
        button = _button_from_element(el)

        if not _is_visible_enabled(button):
            return -9999

        if _is_probably_disabled(sb, button):
            return -9999

        button_text = _norm(_safe_element_text(sb, button))
        card_text = _norm(_closest_reward_card_text(sb, button))
        combined = f"{button_text} {card_text}"

        if "collect" not in combined:
            return -9999

        if "more coins" in button_text:
            return -9999

        bad_markers = [
            "buy",
            "checkout",
            "purchase",
            "deposit",
            "store pack",
            "store packs",
        ]
        if any(marker in button_text for marker in bad_markers):
            return -9999

        score = 0

        # Button text quality
        if button_text == "collect":
            score += 100
        elif "collect" in button_text:
            score += 75

        # Prefer the actual Daily Bonus card.
        if "daily bonus" in card_text:
            score += 120

        # Google Grab is valid-looking, but Daily Bonus should win first.
        if "google grab" in card_text:
            score += 30

        # Reward/modal confidence.
        if "free reward" in card_text:
            score += 15
        if "gc" in card_text or "sc" in card_text:
            score += 10

        # Penalize if the surrounding area looks like purchase area.
        if any(marker in card_text for marker in PURCHASE_TEXT_MARKERS):
            score -= 80

        return score

    except StaleElementReferenceException:
        return -9999
    except Exception:
        return -9999


def _click_element_hard(sb: SB, el) -> bool:
    """
    Click with several fallbacks.
    """
    try:
        el = _button_from_element(el)
    except Exception:
        pass

    try:
        sb.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            el,
        )
        sb.wait(0.3)
    except Exception:
        pass

    # Native Selenium click
    try:
        el.click()
        return True
    except Exception:
        pass

    # JS click
    try:
        sb.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass

    # Dispatch mouse event
    try:
        sb.execute_script(
            """
            const el = arguments[0];
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
            el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
            el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            """,
            el,
        )
        return True
    except Exception:
        pass

    return False


def _force_click_xpath(sb: SB, xpath: str, timeout: float = 10) -> bool:
    """
    Try hard to click an element by XPath.
    Returns True if any strategy succeeds, False otherwise.
    """
    try:
        sb.wait_for_element_visible(xpath, timeout=timeout)
    except Exception:
        return False

    try:
        elements = _find_elements_xpath(sb, xpath)
        for el in elements:
            if _is_visible_enabled(el):
                return _click_element_hard(sb, el)
    except Exception:
        pass

    try:
        sb.scroll_to(xpath)
    except Exception:
        pass

    strategies = ("click", "slow", "js", "directjs")
    for mode in strategies:
        try:
            if mode == "click":
                sb.click_xpath(xpath, timeout=4)
            elif mode == "slow":
                sb.slow_click(xpath)
            elif mode == "js":
                sb.js_click(xpath)
            else:
                el = sb.driver.find_element(By.XPATH, xpath)
                el = _button_from_element(el)
                sb.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue

    return False


def _force_click_css(sb: SB, css: str, timeout: float = 10) -> bool:
    """
    Try hard to click an element by CSS selector.
    Returns True if any strategy succeeds, False otherwise.
    """
    try:
        sb.wait_for_element_visible(css, timeout=timeout)
    except Exception:
        return False

    try:
        elements = _find_elements_css(sb, css)
        for el in elements:
            if _is_visible_enabled(el):
                return _click_element_hard(sb, el)
    except Exception:
        pass

    try:
        sb.scroll_to(css)
    except Exception:
        pass

    strategies = ("click", "slow", "js", "directjs")
    for mode in strategies:
        try:
            if mode == "click":
                sb.click(css)
            elif mode == "slow":
                sb.slow_click(css)
            elif mode == "js":
                sb.js_click(css)
            else:
                el = sb.driver.find_element(By.CSS_SELECTOR, css)
                el = _button_from_element(el)
                sb.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue

    return False


def _build_predictive_collect_xpaths():
    """
    Predictive fallback for common dialog-index / section-index drift.

    Your copied XPath:
    /html/body/div[7]/div/div/section[3]/div/div/div[1]/div/div[3]/button[1]/div[1]

    These try nearby body div indexes, nearby sections, and nearby reward cards.
    """
    xpaths = []

    body_div_indexes = range(4, 11)
    section_indexes = range(2, 5)
    card_indexes = range(1, 5)

    for body_div in body_div_indexes:
        for section in section_indexes:
            for card in card_indexes:
                base_button = (
                    f"/html/body/div[{body_div}]/div/div/"
                    f"section[{section}]/div/div/div[{card}]/div/div[3]/button[1]"
                )

                xpaths.append(base_button)
                xpaths.append(base_button + "/div[1]")

    return xpaths


def _collect_candidates_from_css(sb: SB):
    candidates = []

    for css in COLLECT_CSS_CANDIDATES:
        for el in _find_elements_css(sb, css):
            try:
                button = _button_from_element(el)
                if button not in candidates:
                    candidates.append(button)
            except Exception:
                continue

    return candidates


def _collect_candidates_from_xpath(sb: SB):
    candidates = []

    for xp in COLLECT_XPATH_CANDIDATES:
        for el in _find_elements_xpath(sb, xp):
            try:
                button = _button_from_element(el)
                if button not in candidates:
                    candidates.append(button)
            except Exception:
                continue

    for xp in _build_predictive_collect_xpaths():
        for el in _find_elements_xpath(sb, xp):
            try:
                button = _button_from_element(el)
                if button not in candidates:
                    candidates.append(button)
            except Exception:
                continue

    return candidates


def _collect_candidates_by_text_scan(sb: SB):
    """
    Last broad fallback:
    scan all buttons and button-like elements, then score anything with Collect.
    """
    xpaths = [
        "//button",
        "//*[@role='button']",
        "//*[contains(@class,'button')]",
        "//*[contains(@class,'button-content')]",
    ]

    candidates = []

    for xp in xpaths:
        for el in _find_elements_xpath(sb, xp):
            try:
                text = _norm(_safe_element_text(sb, el))
                if "collect" not in text:
                    continue

                button = _button_from_element(el)
                if button not in candidates:
                    candidates.append(button)
            except Exception:
                continue

    return candidates


def _get_best_collect_candidate(sb: SB):
    """
    Candidacy system:
    collect candidates from exact CSS, exact XPath, predicted XPath,
    and broad text scan, then score and choose best.
    """
    candidates = []

    for source in (
        _collect_candidates_from_css,
        _collect_candidates_from_xpath,
        _collect_candidates_by_text_scan,
    ):
        try:
            for el in source(sb):
                if el not in candidates:
                    candidates.append(el)
        except Exception:
            continue

    scored = []

    for el in candidates:
        score = _score_collect_candidate(sb, el)
        if score > -9999:
            scored.append((score, el))

    if not scored:
        return None, []

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1], scored


def _detect_claim_state(sb: SB) -> dict:
    """
    Small page-state detector so failures are more useful.
    """
    text = _norm(_page_text(sb))

    return {
        "has_claim_free_rewards": "claim free rewards" in text,
        "has_collect": "collect" in text,
        "has_claimed_marker": any(marker in text for marker in CLAIMED_TEXT_MARKERS),
        "has_purchase_marker": any(marker in text for marker in PURCHASE_TEXT_MARKERS),
        "url": sb.get_current_url() if hasattr(sb, "get_current_url") else "",
    }


def _click_best_collect_button(sb: SB) -> bool:
    """
    Main Collect clicker.

    Order:
    1. Use candidate/scoring system.
    2. If no candidate, try exact inspected XPath.
    3. If still no candidate, try old-school CSS force click.
    """
    best, scored = _get_best_collect_candidate(sb)

    if best is not None:
        return _click_element_hard(sb, best)

    # Exact inspected XPath fallback.
    for xp in [INSPECTED_COLLECT_BUTTON_XP, INSPECTED_COLLECT_TEXT_XP]:
        if _force_click_xpath(sb, xp, timeout=2):
            return True

    # CSS fallback.
    for css in [COLLECT_BTN_CSS, COLLECT_BTN_TEXT_CSS]:
        if _force_click_css(sb, css, timeout=2):
            return True

    return False


# ───────────────────────────────────────────────────────────
# American Luck Main flow (UC mode)
# ───────────────────────────────────────────────────────────

async def americanluck_uc(ctx, channel: discord.abc.Messageable):
    await channel.send("Launching **American Luck** (UC)…")

    creds = os.getenv("AMERICANLUCK")
    if not creds or ":" not in creds:
        await channel.send("⚠️ AMERICANLUCK not set in `.env` (expected `email:password`).")
        return

    username, password = creds.split(":", 1)

    sb = None

    try:
        with SB(uc=True, headed=True) as sb:
            # ── Step 1: open login page ──
            sb.uc_open_with_reconnect(LOGIN_URL, 8)
            sb.wait_for_ready_state_complete()

            # ── Step 2: type credentials and click login ──
            # Kept intact from your original flow.
            sb.wait(1)
            sb.type("input[id='emailAddress']", username)
            sb.type("input[id='password']", password)

            # Try to solve captcha via helper, if available.
            try:
                sb.uc_gui_click_captcha()
            except Exception:
                pass

            sb.wait(1.5)

            _force_click_xpath(
                sb,
                "/html/body/div[1]/div[2]/main/div/div/div/div[2]/form/div[4]/button",
                timeout=10,
            )

            sb.wait(6)
            sb.wait_for_ready_state_complete()

            # ── Step 3: close any popup if present ──
            _force_click_xpath(sb, POPUP_CLOSE_XP, timeout=4)

            try:
                sb.press_keys("body", "ESCAPE")
            except Exception:
                pass

            sb.wait(2)
            sb.wait_for_ready_state_complete()

            # ── Step 4: detect login state ──
            login_ok = False

            try:
                sb.wait_for_element_visible(GET_COINS_BTN_XP, timeout=8)
                login_ok = True
            except Exception:
                login_ok = False

            # Fallback: URL heuristic.
            if not login_ok:
                try:
                    current_url = sb.get_current_url()
                    if current_url.startswith(LOBBY_URL):
                        login_ok = True
                except Exception:
                    pass

            if not login_ok:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_login_failed.png",
                    "[American Luck] Login failed or bonus unavailable.",
                )
                return

            # ── Step 5: open Get Coins modal ──
            opened = _force_click_xpath(sb, GET_COINS_BTN_XP, timeout=8)

            if not opened:
                sb.wait(3)
                opened = _force_click_xpath(sb, GET_COINS_BTN_XP, timeout=6)

            if not opened:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_getcoins_missing.png",
                    "[American Luck] Could not open **Get Coins**. "
                    "Layout may have changed or bonus is unavailable.",
                )
                return

            sb.wait_for_ready_state_complete()
            sb.wait(3)

            # ── Step 6: click Collect via candidacy + predictive XPath system ──
            collected = _click_best_collect_button(sb)

            if not collected:
                # Let the lazy-loaded reward cards finish rendering.
                sb.wait(3)
                collected = _click_best_collect_button(sb)

            if not collected:
                # One more small scroll attempt in case the card is below the fold.
                try:
                    sb.execute_script(
                        """
                        const dialog =
                            document.querySelector('div.dialog-container div.free-coin-dialog') ||
                            document.querySelector('div.dialog-container') ||
                            document.scrollingElement;
                        if (dialog) dialog.scrollTop = dialog.scrollHeight;
                        """
                    )
                    sb.wait(1)
                except Exception:
                    pass

                collected = _click_best_collect_button(sb)

            if collected:
                sb.wait(3)
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_claimed.png",
                    "American Luck Daily Bonus Claimed!",
                )
                return

            # ── Step 7: better failure state ──
            state = _detect_claim_state(sb)

            if state["has_claimed_marker"] and not state["has_collect"]:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_already_claimed.png",
                    "[American Luck] Bonus appears to already be claimed.",
                )
                return

            if state["has_claim_free_rewards"] and state["has_purchase_marker"]:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_collect_missing.png",
                    "[American Luck] Get Coins modal opened, but no usable **Collect** button was found. "
                    "The bonus may already be unavailable, or the reward card changed again.",
                )
                return

            await _send_shot(
                sb,
                channel,
                "americanluck_collect_missing.png",
                "[American Luck] Could not find or click **Collect**. "
                "Selector, modal, or reward card layout may have changed.",
            )

    except Exception as e:
        # Top-level crash: try to capture the state for debugging.
        try:
            if sb is not None:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_error.png",
                    f"⚠️ American Luck crashed: `{e}`",
                )
            else:
                await channel.send(
                    f"⚠️ American Luck crashed before browser started: `{e}`"
                )
        except Exception:
            pass