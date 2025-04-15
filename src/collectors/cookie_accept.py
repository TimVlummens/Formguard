"""
Module for finding and accepting cookie consent buttons.
Based on: https://github.com/marty90/priv-accept
"""
import argparse
import os
import sys
import time
from random import randint
from playwright.sync_api import sync_playwright, Page, Locator, Frame, \
    TimeoutError as PlaywrightTimeoutError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import helpers
import re

GLOBAL_SELECTORS = ["button", "a", "div", "span", "form", "p"]
# GLOBAL_SELECTORS = ["button", "link"]
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCEPT_WORDS = f"{MODULE_DIR}/../inject/accept_words.txt"

TIMEOUT = 5000
DEFAULT_TIME_BEFORE_ACCEPTING = 0

CLICK_DWELL_TIME = 100
CLICK_DWELL_TIME_RANGE = 50

CLICK_DWELL_TIME_MIN = CLICK_DWELL_TIME - CLICK_DWELL_TIME_RANGE
CLICK_DWELL_TIME_MAX = CLICK_DWELL_TIME + CLICK_DWELL_TIME_RANGE

class CookieAccepter:
    """
    Class for finding and accepting cookie consent buttons.
    """
    def __init__(self, url, args : dict, log = print):
        self.url = url
        self.args = args
        self._log = log
        self.accept_words_set = set()
        self.accept_words_regex = None

        self.get_accept_words_list()

    def get_accept_words_list(self):
        """
        Reads the file containing the "accept words" and adds the contained entries 
        to create a regex from them.
        The file needs to have each entry on a seperate line.
        """
        ignored_characters = "(✓|\›|!|\\n)*"

        # Match beginning of the string and ignore certain characters
        accept_words_regex = "^"
        accept_words_regex += ignored_characters

        # Add all entries to the regex separated by 'or'
        accept_words_regex += "("
        for w in open(ACCEPT_WORDS, "r", encoding="utf-8").read().splitlines():
            if not w.startswith("#") and not w.strip() == "":
                accept_words_regex += re.escape(w.strip().lower()).replace("/", r"\/")
                accept_words_regex += "|"
                self.accept_words_set.add(w.lower())
        accept_words_regex = accept_words_regex[:-1] + ")"

        # Ignore certain characters and match end of the string
        accept_words_regex += ignored_characters + "$"

        accept_words_regex = re.compile(accept_words_regex, re.IGNORECASE)
        # print("accept_words_regex created")
        self.accept_words_regex = accept_words_regex

    def find_accept_button(self, frame : Frame):
        """
        Find the first selector from GLOBAL_SELECTORS that contains text from the ACCEPT_WORDS_LIST.
        """
        locator = None
        # Search for the first selector containing an entry from the ACCEPT_WORDS_LIST
        locators = frame.get_by_text(self.accept_words_regex)
        # print(locators.count())
        for selector in GLOBAL_SELECTORS:
            # print(selector)
            new_locators = locators.and_(frame.locator(selector))
            # new_locators = frame.locator(selector, has_text=self.accept_words_regex)
            count = new_locators.count()
            # print(count)
            for k in range(count):
                if new_locators.nth(k).is_visible():
                    # print(text)
                    locator = new_locators.nth(k)
                    # print("returning")
                    return locator
            # if locator is not None:
            #     break

        return locator

    def accept_cookies(self, page : Page, locator : Locator):
        """
        Accept cookies by clicking the given locator.
        """
        try:
            self._log(f"🍪 Attempting to accept cookie policy on {self.url}.")
            box = locator.bounding_box()
            # explicit wait for navigation as some pages will reload after accepting cookies
            with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUT):
                # Create coordinates for where to click the button in a rectangle around the center
                x_coord = randint(int(box["x"] + box["width"]/4), \
                                  int(box["x"] + 3*(box["width"]/4)))
                y_coord = randint(int(box["y"] + box["height"]/4), \
                                  int(box["y"] + 3*(box["height"]/4)))
                # Move to the center of the locator and click after a small delay
                page.mouse.move(x_coord, y_coord)
                page.wait_for_timeout(randint(CLICK_DWELL_TIME_MIN, CLICK_DWELL_TIME_MAX))
                # Use page.mouse.click() instead of locator.click() in case locator can't be clicked
                page.mouse.click(x_coord, y_coord, \
                                 delay=randint(CLICK_DWELL_TIME_MIN, CLICK_DWELL_TIME_MAX))

                return True
        except PlaywrightTimeoutError:
            self._log(f"🍪 CookieAccepter: No navigation after clicking accept on {self.url}")
            return True

        except Exception as e:
            self._log(f"❌ CookieAccepter: Error clicking consent manager on {self.url}: {e}")
            return False


    def find_and_accept_cookies(self, page : Page, \
                                time_before_accepting : int = DEFAULT_TIME_BEFORE_ACCEPTING, \
                                screenshot_path : str = ""):
        """
        Takes the given page and the ACCEPT_WORDS_LIST to find and accept cookies on the page.
        It will search each of the pages frames recursively until it finds a button.
        It will search for the first "a", "button", "div", "span", "form" or "p" selector
        containing one of the entries in the ACCEPT_WORDS_LIST. It will then move the mouse
        to this position and click the entry. If "screenshot" is true and a path is given,
        screenshots will be taken before and after attempting to accept possible cookies.
        Returns True if succesfully accepted a cookie.
        """
        locator = None
        func_start_time = time.time()

        frames = helpers.dump_frame_tree(page.main_frame)
        # print(len(frames))
        for frame in frames:
            try:
                if frame.url == "":
                    # https://github.com/microsoft/playwright/issues/8943
                    self._log(f"🍪 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                    # print(f"🍪 Frame skipped on {frame.url} due to empty url." + \
                    #       f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                    #       f" , page: {page.url}")
                    continue
                locator = self.find_accept_button(frame)
            except Exception as e:
                self._log(f"🍪 Frame accept button skipped on {frame.url}" + \
                          f" for {self.url} due to error: {e}")
            if locator is not None:
                break

        self._log(f"🍪 find_accept_button took {time.time() - func_start_time:0.1f}" + \
                  f" s for {self.url}")
        # print(f"🍪 find_accept_button took {time.time()-func_start_time}" + \
        #       f" seconds to complete for {self.url}")

        # Take screenshot if specified
        if self.args.get("screenshot") is True and screenshot_path != "":
            page.screenshot(full_page= True, path= screenshot_path + "_pre_consent.png")

        if locator is None:
            self._log(f"🍪 Did not locate an accept button on {self.url}")
            # print(f"🍪 Did not locate an accept button on {self.url}")
            return False

        # Highlight the locator in debug mode
        if self.args.get("debug"):
            locator.highlight()
            page.wait_for_timeout(1000)

        # Wait between detecting the button and clicking it if necessary
        search_end_time = time.time()
        if time_before_accepting - (search_end_time - func_start_time) >= 0:
            page.wait_for_timeout(time_before_accepting - (search_end_time - func_start_time))

        # Try to click accept button if one is found
        success = self.accept_cookies(page, locator)

        if success:
            self._log(f"🍪 Accepted cookies on {self.url}")

        # Take screenshot if specified
        if self.args.get("screenshot") is True and screenshot_path != "":
            page.screenshot(full_page= True, path=screenshot_path + "_post_consent.png")

        func_end_time = time.time()
        self._log(f"🍪 find_and_accept_cookies took {func_end_time - func_start_time:0.1f}" + \
                  f" s on {self.url}")
        return success
