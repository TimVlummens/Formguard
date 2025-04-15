"""
Main module to run the crawl.
"""
import time
import functools
import logging
import traceback
import helpers
from multiprocessing import cpu_count
from playwright.sync_api import sync_playwright

from pebble import ProcessPool
from concurrent.futures import TimeoutError as PebbleTimeoutError

try:
    from pyvirtualdisplay import Display
except ImportError:  # optional dependency, we can ignore it
    pass


from crawl_url_handler import CrawlUrlHandler
from collectors.login_signup_page_collector import LoginSignupPageCollector
from collectors.form_finder import register_selectors

FORMATTER = logging.Formatter('%(message)s')
# "print" , "text" , "logger"
# LOG_METHOD = "logger"

PRINT_INTERVAL = 100

def create_logger(url, name, filename, level=logging.INFO):
    """
    Function to set up logger for given filename.
    """
    log_filename = filename + ".log"
    handler = logging.FileHandler(log_filename, mode='w', encoding='utf-8')
    handler.setFormatter(FORMATTER)

    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(level)
    logger.addHandler(handler)

    logger.info(f"ℹ️ Log file for {url} ℹ️\n")

    return logger.info

def close_logger(name, timeout : bool = False):
    """
    Close the filehandler of the logger.
    """
    logger = logging.getLogger(name)
    if timeout:
        logger.info(f"❌ A timeout occured for {name}")
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])
    logger.propagate = True

def create_log_file(url, filename):
    """
    Function to set up a text file to which the information can be logged.
    """
    log_filename = filename + "_log.txt"
    helpers.create_url_log_file(url, log_filename)
    log = functools.partial(helpers.append_to_file, log_filename)

    return log

def run_crawl(crawl_details : tuple):
    """
    Handle the crawl for the given url and arguments.
    """
    try:
        url = crawl_details[0]
        args = crawl_details[1]

        url = helpers.append_http(url)
        url_start_time = time.time()
        # print("URL: ", url)

        with sync_playwright() as pw:
            register_selectors(pw)
            try:
                _filepath, filename = helpers.get_filepath_from_url(url, args)

                log = create_logger(url, url, filename)

                login_collector = LoginSignupPageCollector(log)

                crawl_handler = CrawlUrlHandler(pw, login_collector, url, args, log)
                data = crawl_handler.launch_crawl()

                url_end_time = time.time()
                crawl_time = url_end_time-url_start_time
                log_line = f"📃 {url} took {crawl_time:0.1f} s"
                print(log_line)
                log(log_line)

                if data is None:
                    # if LOG_METHOD == "logger":
                    close_logger(url)
                    return (url, "navigation")
                helpers.save_data_to_json(data, filename)

                if not args["record_full"]:
                    helpers.remove_content_from_har(filename, log)
                
                # if LOG_METHOD == "logger":
                close_logger(url)

                if args["mode"] == "replay" or args["mode"] == "record_replay":
                    # Check if the visited url had at least one instruction that timed out
                    if data.get("general") is not None and \
                        data["general"].get("timed_out_instructions") is not None and \
                            len(data["general"]["timed_out_instructions"]) != 0:
                        return (url, "timeout")

                return (url, "success")

            except Exception as e:
                traceback.print_exception(type(e), e, e.__traceback__, None)
                crawl_duration = time.time() - url_start_time
                log_line = f"❌ Crawl for {url} took {crawl_duration:0.1f}s and failed due to Error: {e}"
                # if LOG_METHOD == "logger":
                try:
                    logger = logging.getLogger(url)
                    logger.exception(log_line)
                    close_logger(url)
                except:
                    pass
                return (url, "crawl")
    except Exception as e:
        traceback.print_exception(type(e), e, e.__traceback__, None, )
        print(f"❌ Crawl for {url} failed due to Error: {e}")
        return (url, "navigation")

def main(args = None):
    """
    Main crawl function
    """
    if args is None:
        args = helpers.setup_arg_parser()
        # Return if config file was created.
        if args is None:
            print("Config file created. Will quit.")
            return

    print(args)

    crawl_start_time = time.time()
    use_virtual_display = args.get("headless")
    if use_virtual_display:
        print("📺 Starting the virtual display")
        disp = Display(size = (1280, 720))
        disp.start()


    if args.get("mode") == "record_replay" or \
            (args.get("mode") == "replay" and not args.get("replay_multiple")) or \
            (args.get("url") is not None and args["url"] != "" and \
             args.get("mode") not in ["replay", "record_replay"]):
        if args.get("mode") == "record_replay" or args.get("mode") == "replay":
            filename = helpers.make_filename("codegen")
            url = "codegen"
        else:
            url = args["url"]
            _filepath, filename = helpers.get_filepath_from_url(url, args)

        helpers.create_appended_site_files(args["output_path"])

        crawl_details = (url, args)

        url, code = run_crawl(crawl_details)

        helpers.append_to_sites_file(args["output_path"], url, code)

        # helpers.save_data_to_json(info)

    elif args.get("mode") == "replay" and args.get("replay_multiple"):
        filename = helpers.make_filename("codegen")

        helpers.create_appended_site_files(args["output_path"])
        instruction_timeouts = []

        replay_files = helpers.get_replay_files_from_path(args["replay_path"])

        for replay_file in replay_files:
            print(replay_file)
            url = replay_file[len(args["replay_path"]):-4]
            print(url)
            new_args = args.copy()
            new_args["replay_path"] = replay_file

            crawl_details = (url, new_args)

            url, code = run_crawl(crawl_details)

            helpers.append_to_sites_file(args["output_path"], url, code)

            if code == "timeout":
                instruction_timeouts.append(url)

        print("Sites with timeout: ", instruction_timeouts)

    elif args.get("list") is not None and args["list"]!= "":
        counter = 0

        output_path = args["output_path"]
        urls = helpers.get_urls_from_file(args["list"])

        crawl_details = []

        if args["resume"]:
            # Read in urls and skip already completed sites.
            # Do not reset site list files
            completed_urls = helpers.read_appended_site_files(output_path)
            print(completed_urls)
            skipped_urls = 0

            for url in urls:
                appended_url = helpers.append_http(url)
                if appended_url in completed_urls or url in completed_urls:
                    skipped_urls += 1
                    # print("Skipping ", url)
                else:
                    crawl_details.append((url, args))
            print(f"{skipped_urls} will be skipped.")
        else:
            # Read in all urls
            # Reset site list files
            for url in urls:
                crawl_details.append((url, args))

            helpers.create_appended_site_files(output_path)

        crawl_length = len(crawl_details)

        print(f"Will crawl {crawl_length} sites.")

        with ProcessPool(max_workers=int(cpu_count()*args["cpu_slice"])) as pool:
            future = pool.map(run_crawl, crawl_details, timeout = args["crawl_max_duration"])
            crawl_results = future.result()

            while counter < crawl_length:
                counter += 1

                try:
                    crawl_result = crawl_results.next()

                    if crawl_result is None:
                        continue

                    url, code = crawl_result

                    helpers.append_to_sites_file(output_path, url, code)

                except PebbleTimeoutError as e:
                    url = crawl_details[counter-1][0]
                    helpers.append_to_sites_file(output_path, url, "timeout")
                    traceback.print_exception(type(e), e, e.__traceback__, None)

                    # if LOG_METHOD == "logger":
                    try:
                        logger = logging.getLogger(url)
                        logger.exception(f"Crawl for {url} failed due to Error:")
                        close_logger(url, timeout=True)
                    except:
                        pass

                if not counter % PRINT_INTERVAL:
                    passed_time = time.time() - crawl_start_time
                    print(f"\n\nCrawled {counter} sites in {passed_time:0.1f} s.\n\n")

    else:
        print("No URL or List provided")

    crawl_end_time = time.time()
    crawl_duration = crawl_end_time - crawl_start_time
    print(f"📃 Total crawl took {crawl_duration:0.1f} s")
    if use_virtual_display:
        disp.stop()


if __name__ == "__main__":
    main()
