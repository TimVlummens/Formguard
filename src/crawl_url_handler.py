"""
Module to handle a single url.
"""
import time
from playwright.sync_api import sync_playwright, Playwright

# pylint: disable=import-error
import helpers
from collectors import form_interactor, codegen_parser
from collectors.form_finder import FormFinder
from collectors.cookie_accept import CookieAccepter
from collectors.api_collector import ApiCollector
from collectors.websocket_collector import WebsocketCollector
from collectors.login_signup_page_collector import LoginSignupPageCollector
from collectors.script_collector import ScriptCollector

DEFAULT_VIEWPORT = {'width': 1280, 'height': 720}

INITIAL_WAIT_TIME = 1000
TIME_BEFORE_NEXT = 1000
TIME_BEFORE_CLOSING = 3000

FIELDS_TO_FILL = 0

WINDOW_POSITION_X = 3000
WINDOW_POSITION_Y = 0

class CrawlUrlHandler:
    """
    Class to handle a single url crawl
    """
    def __init__(self, pw : Playwright, login_collector : LoginSignupPageCollector, \
                 url : str, args : dict, log = print):
        self.pw = pw
        self.args = args
        self._log = log

        self.url = helpers.append_http(url)
        self.filepath, self.filename = helpers.get_filepath_from_url(self.url, args)
        self.video_name = self.filepath if args["video"] else ""

        if args["mode"] == "record_replay" and args["record_with_firefox"]:
            self.browser = self.launch_browser(firefox=True)
        else:
            self.browser = self.launch_browser()
        self.cookie_accepter = CookieAccepter(self.url, args, log)
        self.context, self.page = self.launch_page(self.filename, self.video_name)

        if args["mode"] != "record_replay" or not args["record_with_firefox"]:
            self.cdp_client = self.page.context.new_cdp_session(self.page)
            self.api_collector = ApiCollector(self.cdp_client, self.url, self.args, log)
            self.script_collector = ScriptCollector(self.cdp_client, self.args, log)
        self.websocket_collector = WebsocketCollector(self.page, self.url, log)
        self.login_collector = login_collector
        self.login_collector.add_scripts_before_navigation(self.page, self._log)
        self.form_finder = FormFinder(self.pw, self.page, self.args, self._log)

    def launch_browser(self, firefox : bool = False):
        """
        Creates and returns a playwright browser with thespecified browser type and headed/headless
        mode.
        """
        browser_type = self.pw.chromium
        if firefox:
            browser_type = self.pw.firefox
        browser_args= [f"--window-position={self.args['window_pos_x']},{self.args['window_pos_y']}"]


        browser = browser_type.launch(args=browser_args, headless=self.args["headless"])
        return browser

    def launch_page(self, record_requests_path : str = "", record_video_path : str = ""):
        """
        Creates and returns a playwright context and page with recording of requests saved in the
        specified path.
        """
        data = {"viewport": DEFAULT_VIEWPORT}
        if record_requests_path != "" and self.args["mode"] != "compare_detection":
            data["record_har_path"] = record_requests_path + ".har"
        if record_video_path != "":
            data["record_video_dir"] = record_video_path
            data["record_video_size"] = DEFAULT_VIEWPORT
        context = self.browser.new_context(**data)

        page = context.new_page()

        return context, page

    def navigate_to_url(self, url : str):
        """
        Tries to navigate to the given url.
        """
        try:
            self._log(f"📃 Navigating to: {url}")
            self.page.goto(url)
            self.page.wait_for_load_state("load")

            self.url = self.page.url
        except Exception as e:
            self._log(f"❌ Error when navigating to {url} : {e}")
            return False
        return True

    def perform_codegen(self):
        """
        Load codegen file and perform the included instructions.
        """
        instructions = codegen_parser.load_codegen_steps(self.args["replay_path"], \
                                                         self.args["default_exact"])
        options = {"clear_fields": self.args["clear_fields"],
                   "substitute_frames": self.args["substitute_frames"]}
        filled_values, url, final_url, timed_out_instructions, timestamps = \
            codegen_parser.execute_codegen_instructions(self.page, instructions, self._log, options)
        return filled_values, url, final_url, timed_out_instructions, timestamps

    def perform_interaction(self):
        """
        Interact with a given page.
        """
        filled_values = []
        form_interactor.scroll_to_bottom(self.page, self._log)
        fields = self.form_finder.get_fillable_password_email_fields(self.page)
        email_to_fill = form_interactor.get_email_to_fill(self.page.url)
        filled_values, submit_timestamp = \
            form_interactor.fill_fields(fields, self.page, self._log, max_fields=FIELDS_TO_FILL, \
                                        email_input=email_to_fill)
        self.page.wait_for_timeout(1000)
        return filled_values, submit_timestamp

    def perform_crawl(self):
        """
        Performs the crawl for a given page by calling the correct functions in order.
        Crawler will take screenshots before and after attempting to accept possible
        cookies if "screenshot" is true. Files will be named after the URL being visited.
        """
        filled_pages = 0
        filled_values = []
        submit_timestamps = []
        cookie_was_accepted = False
        # page_url = page.url
        self.page.wait_for_timeout(INITIAL_WAIT_TIME)
        if self.args["accept_cookies"]:
            cookie_was_accepted = \
                self.cookie_accepter.find_and_accept_cookies(self.page, \
                                                             screenshot_path=self.filename)
        self.page.wait_for_timeout(TIME_BEFORE_NEXT)

        prediction_result = self.login_collector.get_prediction_result(self.page, self._log)
        if prediction_result:
            filled_value, submit_timestamp = self.perform_interaction()
            filled_values += filled_value
            submit_timestamps.append(submit_timestamp)
            filled_pages += 1

            if self.args["mode"] == "limit_filled" and filled_pages >= self.args["amount"]:
                self.page.wait_for_timeout(TIME_BEFORE_CLOSING)
                return filled_values, submit_timestamps, cookie_was_accepted

        if self.args["mode"] == "landing_page":
            self.page.wait_for_timeout(TIME_BEFORE_CLOSING)
            return filled_values, submit_timestamps, cookie_was_accepted
        # else:
        links = None
        self._log(f"📃 Navigating to other links for {self.url}")
        try:
            links = self.login_collector.get_links(self.page, self._log)
        except Exception as e:
            self._log(f"❌ Error finding links for {self.url} , {e}")

        if links is not None and len(links) > 0:
            self._log(f"📃 Starting navigation for {self.url}")

            for link in links:
                navigation = self.navigate_to_url(link)
                if not navigation:
                    continue

                self.page.wait_for_timeout(INITIAL_WAIT_TIME)
                try:
                    prediction_result = self.login_collector.get_prediction_result(self.page, self._log)
                    if prediction_result:
                        filled_value, submit_timestamp = self.perform_interaction()
                        filled_values += filled_value
                        submit_timestamps.append(submit_timestamp)
                        filled_pages += 1

                        if self.args["mode"] == "limit_filled" and filled_pages >= self.args["amount"]:
                            self.page.wait_for_timeout(TIME_BEFORE_CLOSING)
                            return filled_values, submit_timestamps, cookie_was_accepted
                except Exception as e:
                    self._log(f"❌⚠️ Error interacting with page on {link} for {self.url}: {e}")

        self.page.wait_for_timeout(TIME_BEFORE_CLOSING)
        return filled_values, submit_timestamps, cookie_was_accepted

    def perform_comparison(self):
        """
        Performs comparison of three detection methods for a given page by calling the correct
        functions in order.
        Crawler will take screenshots before and after attempting to accept possible
        cookies if "screenshot" is true. Files will be named after the URL being visited.
        """
        found_fields = {}
        cookie_was_accepted = False
        has_less = False
        # page_url = page.url
        self.page.wait_for_timeout(INITIAL_WAIT_TIME)
        if self.args["accept_cookies"]:
            cookie_was_accepted = \
                self.cookie_accepter.find_and_accept_cookies(self.page, \
                                                             screenshot_path=self.filename)
        self.page.wait_for_timeout(TIME_BEFORE_NEXT)

        prediction_result = self.login_collector.get_prediction_result(self.page, self._log)
        if prediction_result:
            data = self.form_finder.compare_detections(self.page)
            found_fields[self.page.url] = data
            if data["comparison"] == "less":
                has_less = True

        self._log(f"📃 Navigating to other links for {self.url}")
        links = None
        try:
            links = self.login_collector.get_links(self.page, self._log)
        except:
            pass
        if links is not None:
            for link in links:
                navigation = self.navigate_to_url(link)
                if not navigation:
                    continue

                self.page.wait_for_timeout(INITIAL_WAIT_TIME)
                try:
                    prediction_result = self.login_collector.get_prediction_result(self.page, self._log)
                    if prediction_result:
                        data = self.form_finder.compare_detections(self.page)
                        found_fields[self.page.url] = data
                        if data["comparison"] == "less":
                            has_less = True
                except Exception as e:
                    self._log(f"❌⚠️ Error comparing detection on {link} for {self.url}: {e}")

        self.page.wait_for_timeout(TIME_BEFORE_CLOSING)
        return found_fields, cookie_was_accepted, has_less

    def launch_crawl(self):
        """
        Performs the necessary steps for a given url.
        The handler will close the created page, context and browser and is unusable afterwards.
        """
        crawl_start_timestamp = time.time()

        filled_values = []
        submit_timestamps = []
        timestamps = []
        cookie_was_accepted = False
        found_fields = {}
        has_less = False
        codegen_url = ""
        timed_out_instructions = []

        if self.args["mode"] == "record_replay":
            print(" Waiting for user input.\n Please record the prefered actions to be taken.\n"+ \
                " Paste the recorded code in the file specified in the given argumetns.\n"+ \
                " Close the page to end the recording.")
            self.page.pause()
            final_url = self.url

            # Start new browser to reset all cookies
            self.browser.close()
            self.browser = self.launch_browser()
            # Re-setup required classes
            self.context, self.page = self.launch_page(self.filename, self.video_name)
            self.cdp_client = self.page.context.new_cdp_session(self.page)
            self.api_collector = ApiCollector(self.cdp_client, self.url, self.args, self._log)
            self.script_collector = ScriptCollector(self.cdp_client, self.args, self._log)
            self.websocket_collector = WebsocketCollector(self.page, self.url, self._log)
            self.form_finder = FormFinder(self.pw, self.page, self.args, self._log)

            filled_values, codegen_url, final_url, timed_out_instructions, timestamps = \
                self.perform_codegen()
            # Leave page open after codegen
            if self.args["wait_for_close"]:
                print("\n\n\nClose the page to save data and finish program.\n\n\n")
                self.page.wait_for_event("close", timeout=0)
            else:
                self.page.wait_for_timeout(5000)

        elif self.args["mode"] == "replay":
            filled_values, codegen_url, final_url, timed_out_instructions, timestamps = \
                self.perform_codegen()
            # Leave page open after codegen
            if self.args["wait_for_close"]:
                print("\n\n\nClose the page to save data and finish program.\n\n\n")
                self.page.wait_for_event("close", timeout=0)
            else:
                self.page.wait_for_timeout(5000)
        else:
            navigation = self.navigate_to_url(self.url)
            if not navigation:
                self.context.close()
                self.page.close()
                if self.args.get("video") is not None and self.args["video"] is True:
                    # Delete the randomly named version
                    self.page.video.delete()
                return None
            final_url = self.url
            if self.args["mode"] != "compare_detection":
                filled_values, submit_timestamps, cookie_was_accepted = self.perform_crawl()
            else:
                found_fields, cookie_was_accepted, has_less = self.perform_comparison()

        crawl_end_time = time.time()
        general_data = {"start_time": crawl_start_timestamp, "end_time": crawl_end_time, \
                        "page_url": final_url, "cookie_was_accepted": cookie_was_accepted, \
                        "mode": self.args["mode"]}

        if self.args["mode"] == "replay" or self.args["mode"] == "record_replay":
            general_data["codegen_url"] = codegen_url
            general_data["timed_out_instructions"] = timed_out_instructions
            general_data["timestamps"] = timestamps

        if self.args["mode"] == "compare_detection":
            data = {"general": general_data, "has_less": has_less, "found_fields": found_fields}
        else:
            data = {"apis": self.api_collector.get_api_collector_data(),
                    "websockets": self.websocket_collector.get_websocket_collector_data(),
                    "scripts": self.script_collector.get_scripts(),
                    "general": general_data,
                    "filled_values": filled_values,
                    "submit_timestamps": submit_timestamps
                    }

        self.page.close()
        if self.args.get("video") is not None and self.args["video"] is True:
            # Save video as file named after url and delete the randomly named version
            self.page.video.save_as(self.filename + ".mp4")
            self.page.video.delete()

        self.context.close()
        self.browser.close()

        print("Finished crawl for: ", final_url)
        return data
