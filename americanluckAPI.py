# Drake Hooks + WaterTrooper
# Casino Claim 2
# American Luck API (SeleniumBase UC)
#
# Fixes:
# - Detects and closes the "Connect with Google" / pre-connect popup before Get Coins.
# - Uses exact popup close XPath /html/body/div[5]/div/button, but only when the Google popup is detected.
# - Adds generic blocking-popup detection for similar future popups.
# - Opens Get Coins with retries after popup cleanup.
# - Claims ONLY the Daily Bonus card's Collect button.
# - Refuses Google Grab, More Coins, Connect with Google, Buy, Checkout, etc.

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

GET_COINS_BTN_XP = "/html/body/div[1]/div[2]/header/div[2]/button[1]"

# Correct blocker popup close XPath from your screenshot.
GOOGLE_PRECONNECT_CLOSE_XP = "/html/body/div[5]/div/button"

# Older/general popup close path. Kept as fallback, but guarded.
POPUP_CLOSE_XP = "/html/body/div[5]/div/button"

# Correct Daily Bonus collect XPath from your inspection.
DAILY_BONUS_EXACT_BUTTON_XP = (
    "/html/body/div[7]/div/div/section[3]/div/div/div[1]/div/div[3]/button[1]"
)

DAILY_BONUS_EXACT_TEXT_XP = (
    "/html/body/div[7]/div/div/section[3]/div/div/div[1]/div/div[3]/button[1]/div[1]"
)

# Main text-anchored Daily Bonus selector.
DAILY_BONUS_CARD_XP = (
    "//div[contains(@class,'dialog-container')]"
    "//div[contains(@class,'free-reward-card')]"
    "[.//*[contains(@class,'free-reward-card__title') "
    "and translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='daily bonus']]"
)

DAILY_BONUS_COLLECT_BUTTON_XP = (
    DAILY_BONUS_CARD_XP +
    "//button"
    "[contains(@class,'free-reward-card__button') "
    "and contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect') "
    "and not(contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more coins'))]"
)

DAILY_BONUS_COLLECT_TEXT_XP = (
    DAILY_BONUS_CARD_XP +
    "//*[contains(@class,'button-content') "
    "and translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='collect']"
    "/ancestor::button[1]"
)

DAILY_BONUS_CSS_CARD = "div.free-reward-card"
DAILY_BONUS_CSS_TITLE = ".free-reward-card__title"
DAILY_BONUS_CSS_BUTTONS = "button.free-reward-card__button, button.rag-button"

FREE_COIN_DIALOG_CSS = "div.free-coin-dialog"

BLOCKING_POPUP_MARKERS = [
    "connect with google",
    "google rewards",
    "connect your google account",
    "lucrative bonus",
    "pre connect",
    "pre-connect",
]

CLAIMED_TEXT_MARKERS = [
    "today's bonus is claimed",
    "todays bonus is claimed",
    "bonus is claimed",
    "already claimed",
    "claimed",
]

BAD_BUTTON_TEXT_MARKERS = [
    "more coins",
    "google",
    "connect",
    "buy",
    "checkout",
    "purchase",
    "deposit",
    "store pack",
    "store packs",
]


# ───────────────────────────────────────────────────────────
# Generic Helpers
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
        return sb.execute_script(
            "return arguments[0].innerText || arguments[0].textContent || '';",
            el,
        ) or ""
    except Exception:
        return ""


def _page_text(sb: SB) -> str:
    try:
        return sb.execute_script(
            "return document.body ? document.body.innerText : '';"
        ) or ""
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


def _is_probably_disabled(el) -> bool:
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


def _click_element_hard(sb: SB, el) -> bool:
    try:
        el = _button_from_element(el)
    except Exception:
        pass

    try:
        sb.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});",
            el,
        )
        sb.wait(0.35)
    except Exception:
        pass

    try:
        el.click()
        return True
    except Exception:
        pass

    try:
        sb.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass

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

    for mode in ("click", "slow", "js", "directjs"):
        try:
            if mode == "click":
                sb.click_xpath(xpath, timeout=4)
            elif mode == "slow":
                sb.slow_click(xpath)
            elif mode == "js":
                sb.js_click(xpath)
            else:
                el = sb.driver.find_element(By.XPATH, xpath)
                sb.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue

    return False


# ───────────────────────────────────────────────────────────
# Blocking Popup Manager
# ───────────────────────────────────────────────────────────

def _has_blocking_google_popup(sb: SB) -> bool:
    text = _norm(_page_text(sb))
    return any(marker in text for marker in BLOCKING_POPUP_MARKERS)


def _is_get_coins_modal_open(sb: SB) -> bool:
    try:
        dialogs = _find_elements_css(sb, FREE_COIN_DIALOG_CSS)
        for dialog in dialogs:
            if dialog.is_displayed():
                return True
    except Exception:
        pass

    text = _norm(_page_text(sb))
    return "claim free rewards" in text and "purchase store packs" in text


def _close_blocking_popup_with_js(sb: SB) -> bool:
    """
    Generic popup closer.

    It only targets popup/modal roots containing blocking Google/pre-connect text.
    It intentionally avoids the Get Coins free-coin dialog.
    """
    try:
        return bool(
            sb.execute_script(
                """
                const markers = [
                    'connect with google',
                    'google rewards',
                    'connect your google account',
                    'lucrative bonus',
                    'pre connect',
                    'pre-connect'
                ];

                const lower = s => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();

                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return (
                        r.width > 0 &&
                        r.height > 0 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        style.opacity !== '0'
                    );
                };

                const roots = [...document.querySelectorAll(
                    "div[class*='popup'], div[class*='modal'], div[role='dialog'], div[class*='backdrop']"
                )].filter(visible);

                for (const root of roots) {
                    const rootClass = lower(root.className);
                    const txt = lower(root.innerText || root.textContent || '');

                    // Do not close the real Get Coins modal.
                    if (rootClass.includes('free-coin-dialog')) {
                        continue;
                    }

                    if (!markers.some(m => txt.includes(m))) {
                        continue;
                    }

                    const buttons = [...root.querySelectorAll('button')].filter(visible);

                    const closeBtn =
                        buttons.find(b => {
                            const cls = lower(b.className);
                            const aria = lower(b.getAttribute('aria-label'));
                            const title = lower(b.getAttribute('title'));
                            return (
                                cls.includes('close') ||
                                aria.includes('close') ||
                                title.includes('close')
                            );
                        }) ||
                        buttons.find(b => {
                            // Fallback for icon-only X buttons.
                            const cls = lower(b.className);
                            const rect = b.getBoundingClientRect();
                            const rootRect = root.getBoundingClientRect();

                            const nearTopRight =
                                rect.top <= rootRect.top + 80 &&
                                rect.left >= rootRect.right - 120;

                            return (
                                b.querySelector('svg') &&
                                nearTopRight &&
                                !lower(b.innerText).includes('connect')
                            );
                        });

                    if (closeBtn) {
                        closeBtn.click();
                        return true;
                    }
                }

                return false;
                """
            )
        )
    except Exception:
        return False


def _close_blocking_popup_by_xpath(sb: SB) -> bool:
    """
    XPath-based closer for the known Google popup.
    Uses your exact /html/body/div[5]/div/button path, but only when blocker text exists.
    """
    if not _has_blocking_google_popup(sb):
        return False

    for xp in [
        GOOGLE_PRECONNECT_CLOSE_XP,
        POPUP_CLOSE_XP,
        "//div[contains(@class,'pre-connect-info-dialog-popup')]//button[contains(@class,'close')]",
        "//div[contains(@class,'rag-popup') and .//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'connect with google')]]//button[contains(@class,'close')]",
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'connect with google')]/ancestor::*[contains(@class,'popup') or contains(@class,'modal') or @role='dialog'][1]//button[contains(@class,'close')]",
    ]:
        try:
            if _force_click_xpath(sb, xp, timeout=1.5):
                return True
        except Exception:
            continue

    return False


def _close_blocking_popups(sb: SB, max_rounds: int = 4) -> int:
    """
    Close Google/pre-connect blocker popups before trying Get Coins.

    Returns number of close attempts that succeeded.
    """
    closed_count = 0

    for _ in range(max_rounds):
        if _is_get_coins_modal_open(sb):
            break

        found_blocker = _has_blocking_google_popup(sb)

        if not found_blocker:
            break

        closed = False

        if _close_blocking_popup_by_xpath(sb):
            closed = True
        elif _close_blocking_popup_with_js(sb):
            closed = True
        else:
            try:
                sb.press_keys("body", "ESCAPE")
                sb.wait(0.5)
                closed = not _has_blocking_google_popup(sb)
            except Exception:
                closed = False

        if not closed:
            break

        closed_count += 1
        sb.wait(1)

    return closed_count


def _open_get_coins_modal(sb: SB) -> bool:
    """
    Open Get Coins intelligently.

    It repeatedly:
    - closes blockers,
    - checks if modal is already open,
    - clicks Get Coins,
    - closes any blocker that appeared,
    - confirms the Get Coins modal is open.
    """
    for attempt in range(1, 6):
        sb.wait_for_ready_state_complete()

        _close_blocking_popups(sb, max_rounds=4)

        if _is_get_coins_modal_open(sb):
            return True

        clicked = _force_click_xpath(sb, GET_COINS_BTN_XP, timeout=6)

        sb.wait(1.5)
        sb.wait_for_ready_state_complete()

        # Sometimes clicking Get Coins triggers/reveals the Google popup instead.
        if _has_blocking_google_popup(sb):
            _close_blocking_popups(sb, max_rounds=4)
            sb.wait(1)

        if _is_get_coins_modal_open(sb):
            return True

        # One more try after cleanup.
        if not clicked:
            _close_blocking_popups(sb, max_rounds=4)

        sb.wait(1)

    return _is_get_coins_modal_open(sb)


# ───────────────────────────────────────────────────────────
# Daily Bonus Specific Logic
# ───────────────────────────────────────────────────────────

def _scroll_rewards_into_view(sb: SB):
    try:
        sb.execute_script(
            """
            const title = [...document.querySelectorAll('h2,h3,div,section')]
                .find(el => /claim free rewards/i.test(el.innerText || ''));

            if (title) {
                title.scrollIntoView({block:'center', inline:'center'});
                return;
            }

            const dialog =
                document.querySelector('div.dialog-container div.free-coin-dialog') ||
                document.querySelector('div.dialog-container') ||
                document.scrollingElement;

            if (dialog) {
                dialog.scrollTop = Math.floor(dialog.scrollHeight * 0.70);
            }
            """
        )
        sb.wait(0.75)
    except Exception:
        pass


def _get_card_title(sb: SB, card) -> str:
    try:
        title = card.find_element(By.CSS_SELECTOR, DAILY_BONUS_CSS_TITLE)
        return _norm(_safe_element_text(sb, title))
    except Exception:
        return ""


def _is_daily_bonus_card(sb: SB, card) -> bool:
    title = _get_card_title(sb, card)

    if title == "daily bonus":
        return True

    card_text = _norm(_safe_element_text(sb, card))
    return "daily bonus" in card_text and "google grab" not in card_text


def _get_ancestor_card(sb: SB, el):
    try:
        return el.find_element(
            By.XPATH,
            "./ancestor::*[contains(@class,'free-reward-card')][1]",
        )
    except Exception:
        return None


def _button_belongs_to_daily_bonus(sb: SB, button) -> bool:
    card = _get_ancestor_card(sb, button)

    if card is None:
        return False

    return _is_daily_bonus_card(sb, card)


def _button_text_is_valid_daily_collect(sb: SB, button) -> bool:
    text = _norm(_safe_element_text(sb, button))

    if "collect" not in text:
        return False

    for bad in BAD_BUTTON_TEXT_MARKERS:
        if bad in text:
            return False

    if _is_probably_disabled(button):
        return False

    return True


def _find_daily_bonus_card_by_css(sb: SB):
    cards = _find_elements_css(sb, DAILY_BONUS_CSS_CARD)

    for card in cards:
        try:
            if not card.is_displayed():
                continue

            if _is_daily_bonus_card(sb, card):
                return card
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    return None


def _find_daily_bonus_card_by_xpath(sb: SB):
    cards = _find_elements_xpath(sb, DAILY_BONUS_CARD_XP)

    for card in cards:
        try:
            if card.is_displayed() and _is_daily_bonus_card(sb, card):
                return card
        except Exception:
            continue

    return None


def _find_daily_bonus_card(sb: SB):
    card = _find_daily_bonus_card_by_css(sb)

    if card is not None:
        return card

    return _find_daily_bonus_card_by_xpath(sb)


def _find_collect_button_inside_daily_card(sb: SB, card):
    try:
        buttons = card.find_elements(By.CSS_SELECTOR, DAILY_BONUS_CSS_BUTTONS)
    except Exception:
        buttons = []

    valid = []

    for button in buttons:
        try:
            if not _is_visible_enabled(button):
                continue

            if not _button_text_is_valid_daily_collect(sb, button):
                continue

            if not _button_belongs_to_daily_bonus(sb, button):
                continue

            valid.append(button)
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    if valid:
        return valid[0]

    try:
        xpath_buttons = card.find_elements(
            By.XPATH,
            ".//button"
            "[contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'collect') "
            "and not(contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more coins'))]",
        )

        for button in xpath_buttons:
            if (
                _is_visible_enabled(button)
                and _button_text_is_valid_daily_collect(sb, button)
                and _button_belongs_to_daily_bonus(sb, button)
            ):
                return button
    except Exception:
        pass

    return None


def _find_daily_collect_by_anchored_xpath(sb: SB):
    for xp in [
        DAILY_BONUS_COLLECT_BUTTON_XP,
        DAILY_BONUS_COLLECT_TEXT_XP,
    ]:
        for el in _find_elements_xpath(sb, xp):
            try:
                button = _button_from_element(el)

                if not _is_visible_enabled(button):
                    continue

                if not _button_text_is_valid_daily_collect(sb, button):
                    continue

                if not _button_belongs_to_daily_bonus(sb, button):
                    continue

                return button
            except Exception:
                continue

    return None


def _find_daily_collect_by_exact_xpath_guarded(sb: SB):
    for xp in [
        DAILY_BONUS_EXACT_BUTTON_XP,
        DAILY_BONUS_EXACT_TEXT_XP,
    ]:
        for el in _find_elements_xpath(sb, xp):
            try:
                button = _button_from_element(el)

                if not _is_visible_enabled(button):
                    continue

                if not _button_text_is_valid_daily_collect(sb, button):
                    continue

                if not _button_belongs_to_daily_bonus(sb, button):
                    continue

                return button
            except Exception:
                continue

    return None


def _build_daily_bonus_predictive_xpaths():
    xpaths = []

    body_div_indexes = range(4, 12)
    section_indexes = range(2, 5)
    card_indexes = range(1, 4)

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


def _find_daily_collect_by_predictive_xpath_guarded(sb: SB):
    for xp in _build_daily_bonus_predictive_xpaths():
        for el in _find_elements_xpath(sb, xp):
            try:
                button = _button_from_element(el)

                if not _is_visible_enabled(button):
                    continue

                if not _button_text_is_valid_daily_collect(sb, button):
                    continue

                if not _button_belongs_to_daily_bonus(sb, button):
                    continue

                return button
            except Exception:
                continue

    return None


def _click_daily_bonus_collect(sb: SB) -> bool:
    """
    Correct Daily Bonus clicker.

    It only clicks Collect if the button belongs to the Daily Bonus card.
    """
    if not _is_get_coins_modal_open(sb):
        return False

    _scroll_rewards_into_view(sb)

    card = _find_daily_bonus_card(sb)

    if card is not None:
        button = _find_collect_button_inside_daily_card(sb, card)
        if button is not None:
            return _click_element_hard(sb, button)

    button = _find_daily_collect_by_anchored_xpath(sb)
    if button is not None:
        return _click_element_hard(sb, button)

    button = _find_daily_collect_by_exact_xpath_guarded(sb)
    if button is not None:
        return _click_element_hard(sb, button)

    button = _find_daily_collect_by_predictive_xpath_guarded(sb)
    if button is not None:
        return _click_element_hard(sb, button)

    return False


def _debug_daily_bonus_state(sb: SB) -> str:
    lines = []

    try:
        lines.append(f"blocking_google_popup: {_has_blocking_google_popup(sb)}")
        lines.append(f"get_coins_modal_open: {_is_get_coins_modal_open(sb)}")

        cards = _find_elements_css(sb, DAILY_BONUS_CSS_CARD)
        lines.append(f"reward cards found: {len(cards)}")

        for idx, card in enumerate(cards, start=1):
            try:
                title = _get_card_title(sb, card)
                buttons = card.find_elements(By.CSS_SELECTOR, "button")
                button_texts = [_norm(_safe_element_text(sb, b)) for b in buttons]

                lines.append(
                    f"card {idx}: title={title!r}, "
                    f"buttons={button_texts!r}, "
                    f"is_daily={_is_daily_bonus_card(sb, card)}"
                )
            except Exception as e:
                lines.append(f"card {idx}: debug error={e}")
    except Exception as e:
        lines.append(f"debug error: {e}")

    return "\n".join(lines[-10:])


def _detect_claim_state(sb: SB) -> dict:
    text = _norm(_page_text(sb))

    return {
        "has_blocking_google_popup": _has_blocking_google_popup(sb),
        "has_get_coins_modal": _is_get_coins_modal_open(sb),
        "has_claim_free_rewards": "claim free rewards" in text,
        "has_daily_bonus": "daily bonus" in text,
        "has_google_grab": "google grab" in text,
        "has_collect": "collect" in text,
        "has_claimed_marker": any(marker in text for marker in CLAIMED_TEXT_MARKERS),
        "url": sb.get_current_url() if hasattr(sb, "get_current_url") else "",
    }


# ───────────────────────────────────────────────────────────
# American Luck Main Flow
# ───────────────────────────────────────────────────────────

async def americanluck_uc(ctx, channel: discord.abc.Messageable):
    await channel.send("Launching **American Luck** (UC)…")

    creds = os.getenv("AMERICANLUCK")

    if not creds or ":" not in creds:
        await channel.send("⚠️ AMERICANLUCK not set in `.env`.")
        return

    username, password = creds.split(":", 1)

    sb = None

    try:
        with SB(uc=True, headed=True) as sb:
            # ── Step 1: open login page ──
            sb.uc_open_with_reconnect(LOGIN_URL, 8)
            sb.wait_for_ready_state_complete()

            # ── Step 2: login ──
            sb.wait(1)
            sb.type("input[id='emailAddress']", username)
            sb.type("input[id='password']", password)

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

            # ── Step 3: close blocker popups after login ──
            _close_blocking_popups(sb, max_rounds=5)

            try:
                sb.press_keys("body", "ESCAPE")
            except Exception:
                pass

            sb.wait(1)
            sb.wait_for_ready_state_complete()

            # ── Step 4: verify lobby/login ──
            login_ok = False

            try:
                sb.wait_for_element_visible(GET_COINS_BTN_XP, timeout=8)
                login_ok = True
            except Exception:
                login_ok = False

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
                    "[American Luck] Login failed or lobby did not load.",
                )
                return

            # ── Step 5: intelligently open Get Coins modal ──
            opened = _open_get_coins_modal(sb)

            if not opened:
                debug = _debug_daily_bonus_state(sb)

                await _send_shot(
                    sb,
                    channel,
                    "americanluck_getcoins_missing.png",
                    "[American Luck] Could not open **Get Coins** after popup cleanup.\n\n"
                    f"```{debug[:1500]}```",
                )
                return

            sb.wait_for_ready_state_complete()
            sb.wait(2)

            # Important: do NOT close popups here unless the Google blocker exists.
            # The Get Coins modal itself has a close button, so we avoid blind closing.
            if _has_blocking_google_popup(sb):
                _close_blocking_popups(sb, max_rounds=4)

            # ── Step 6: click ONLY Daily Bonus Collect ──
            collected = _click_daily_bonus_collect(sb)

            if not collected:
                sb.wait(2)
                collected = _click_daily_bonus_collect(sb)

            if not collected:
                _scroll_rewards_into_view(sb)
                sb.wait(1)
                collected = _click_daily_bonus_collect(sb)

            if collected:
                sb.wait(3)

                await _send_shot(
                    sb,
                    channel,
                    "americanluck_claimed.png",
                    "American Luck Daily Bonus Claimed!",
                )
                return

            # ── Step 7: failure/debug ──
            state = _detect_claim_state(sb)
            debug = _debug_daily_bonus_state(sb)

            if state["has_claimed_marker"]:
                await _send_shot(
                    sb,
                    channel,
                    "americanluck_already_claimed.png",
                    "[American Luck] Daily Bonus appears to already be claimed.",
                )
                return

            await _send_shot(
                sb,
                channel,
                "americanluck_daily_collect_missing.png",
                "[American Luck] Could not click **Daily Bonus → Collect**.\n"
                "I refused to click Google Grab, Connect with Google, More Coins, or any non-Daily Bonus button.\n\n"
                f"```{debug[:1500]}```",
            )

    except Exception as e:
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