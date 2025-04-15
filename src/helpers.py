"""
Module with general helper functions.
"""
from urllib.parse import urlparse
import argparse
import os
import json
import yaml
import time
import glob
from os.path import join
from playwright.async_api import Frame, Page

BLOCK_CLOSED_SHADOWS = """
console.log('Switching Attach Shadow');
Element.prototype._attachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function () {
    // console.log('attachShadow');
    return this._attachShadow( { mode: "open" } );
};
"""

MODULE_DIR = os.path.dirname(os.path.abspath(__file__)) + '/'
DEFAULT_OUTPUT_FOLDER = "../output/"

DEFAULT_CONFIG = {"mode": "full",
                  "amount": 3,
                  "headless": True,
                  "window_pos_x": 0,
                  "window_pos_y": 0,
                  "pierce": True,
                  "replay_path": "",
                  "record_with_firefox": False,
                  "replay_multiple": False,
                  "substitute_frames": False,
                  "wait_for_close": True,
                  "screenshot": False,
                  "video": False,
                  "debug": False,
                  "clear_fields": True,
                  "default_exact": False,
                  "accept_cookies": True,
                  "output_path": MODULE_DIR + DEFAULT_OUTPUT_FOLDER,
                  "record_full": False,
                  "resume": False,
                  "cpu_slice": 0.9,
                  "crawl_max_duration": 250
                  }

MODES = {"0": "full",
         "1": "limit_filled",
         "2": "landing_page",
         "3": "record_replay",
         "4": "replay",
         "5": "compare_detection"
         }

OUTPUT_FOLDER = MODULE_DIR + DEFAULT_OUTPUT_FOLDER

def check_config_data(data):
    """
    Function to check data for correctness and force certain values.
    """
    # Check mode
    if data.get("mode") is None:
        raise ValueError("❌ No mode specified in given config file!")
    data["mode"] = str(data["mode"])
    if data["mode"] in MODES:
        data["mode"] = MODES[data["mode"]]

    match data["mode"]:
        case "full" | "limit_filled" | "landing_page":
            has_url = False
            if data.get("url") is not None and data.get("url") != "":
                has_url = True
            if data.get("list") is not None and data.get("list") != "":
                if has_url:
                    raise ValueError("❌ Both a single url and a list is specified!")
                # # Force list to headless
                # if not data["headless"]:
                #     raise ValueError("❌ Lists should be run in headless mode!")
            elif not has_url:
                raise ValueError("❌ No url or list specified in given config file!")
        case "record_replay" | "replay":
            if data["headless"]:
                raise ValueError("❌ Codegen modes should be run in headed mode.")
            if data.get("replay_path") is None or data.get("replay_path") == "":
                raise ValueError("❌ No replay path specified!")
            if data.get("replay_multiple") :
                if data["mode"] != "replay":
                    raise ValueError("❌ Cannot replay multiple in record_replay mode!")
                if not data.get("replay_path").endswith("/") and \
                        not data.get("replay_path").endswith("\\"):
                    raise ValueError("❌ Given replay path does not end in a '/' or a '\\'!")
        case "compare_detection":
            has_url = False
            if data.get("url") is not None and data.get("url") != "":
                has_url = True
            if data.get("list") is not None and data.get("list") != "":
                if has_url:
                    raise ValueError("❌ Both a single url and a list is specified!")
                # Force list to headless
                if not data["headless"]:
                    raise ValueError("❌ Lists should be run in headless mode!")
            elif not has_url:
                raise ValueError("❌ No url or list specified in given config file!")
        case _:
            raise ValueError("❌ Unrecognized mode!")

    if data.get("headless") is True and data["debug"] is True:
        raise ValueError("❌ Headless mode can not be run in debug mode!")

    if data["output_path"] == "":
        raise ValueError("❌ No output path given!")
    elif not (data["output_path"].endswith("/") or data["output_path"].endswith("\\")):
        raise ValueError("❌ Given output path does not end in a '/' or a '\\'!")

    return data

def get_args_from_config(args_given):
    """
    Parse config json or yaml file and return arguments as dict.
    """
    config = args_given.config if args_given.config != "" else "config.json"
    print(config)
    data = DEFAULT_CONFIG

    if config.endswith(".json"):
        with open(join(MODULE_DIR, config), "r", encoding="utf-8") as w:
            new_data = json.loads(w.read())
    elif config.endswith(".yaml"):
        print(f"Reading config file {config}")
        with open(join(MODULE_DIR, config), encoding="utf8") as w:
            try:
                new_data = yaml.safe_load(w)
            except yaml.YAMLError as e:
                print(e)
    else:
        raise ValueError("❌ Invalid file extension.")

    # Make sure default values are kept for unspecified values
    for key in new_data:
        data[key] = new_data[key]

    return check_config_data(data)

def create_default_config(path):
    """
    Create a config value containing default values at the specified (relative) path.
    """
    if path.endswith(".json"):
        with open(MODULE_DIR + path, 'w', encoding="utf-8") as w:
            json.dump(DEFAULT_CONFIG, w, default=tuple)
    elif path.endswith(".yaml") or path.endswith(".yml"):
        with open(MODULE_DIR + path, 'w', encoding='utf8') as w:
            yaml.dump(DEFAULT_CONFIG, w, default_flow_style=False)
    else:
        raise ValueError("❌ Invalid file extension.")

def setup_arg_parser():
    """
    Function sets up argparser with necessary arguments.
    Returns the collected arguments.
    """
    parser=argparse.ArgumentParser()
    # Selection of either config file of generation of empty one
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-config', help="Path to file with config options.")
    group.add_argument('-create', help="Create a default config file at the specified location.")

    data=parser.parse_args()

    if data.config:
        result = get_args_from_config(data)
        return result
    elif data.create:
        create_default_config(data.create)
    else:
        raise ValueError("❌ No valid arguments!")
    return None

def get_urls_from_file(url_list : str):
    """
    Reads the given file and returns the contained URLs as a list.
    The file needs to have each URL on a seperate line.
    """
    urls = set()
    # GA: consider accepting an absolute path for url_list
    for w in open(join(MODULE_DIR, url_list), "r", encoding="utf-8").read().splitlines():
        # Remove commented and empty lines
        if not w.startswith("#") and not w.strip() == '':
            urls.add(w.lower())
    return list(urls)

def get_replay_files_from_path(replay_path : str):
    """
    Return all .txt filenames from the given folder path.
    """
    replay_files = glob.glob(replay_path + '*.txt', recursive = False)
    return replay_files

def append_http(url : str):
    """
    Prepares URL by appending http:// if required.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url

    return url

def get_filepath_from_url(url : str, data : dict):
    """
    Takes given URL and creates filepath string that can be used by other
    functions to save data to a file.
    The path does not end in an extension, this will be added by each function itself.
    """
    url = append_http(url)
    name = urlparse(url).hostname
    output_folder = data.get("output_path")
    return output_folder, output_folder + name

def make_filename(name : str):
    """
    Make absolute filepath for file.
    """
    return OUTPUT_FOLDER + name

def string_to_boolean(v):
    """
    Convert many string options to a boolean value. Useful for argparsing.
    From: https://stackoverflow.com/a/43357954/5761491
    """
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    if v.lower() in ("no", "false", "f", "n", "0"):
        return False

    raise argparse.ArgumentTypeError("Boolean value expected.")

def create_locator_list(new_locators, debug : bool = False, frame : Frame = None):
    """
    Takes a locator pointing to multiple fields.
    Returns a list with one locator for each field.
    Highlights each field if debug.
    """
    locator_list = []
    count = new_locators.count()
    for k in range(count):
        locator = new_locators.nth(k)
        if locator is not None:
            locator_list.append(locator)

            if debug and frame is not None:
                locator.highlight()
                frame.wait_for_timeout(1000)

    return locator_list

def block_closed_shadows(page : Page):
    """
    Inject script to block closed shadow creation.
    """
    page.add_init_script(script=BLOCK_CLOSED_SHADOWS)

def dump_frame_tree(frame):
    """
    Collect all frames on a page by recursively adding all children.
    """
    frames = [frame,]
    for child in frame.child_frames:
        frames += dump_frame_tree(child)

    return frames

def save_data_to_json(data : dict, path : str):
    """
    Write given data in dict format to a json file.
    """
    with open(path + ".json", 'w', encoding="utf8") as fp:
        json.dump(data, fp, default=tuple, sort_keys=True, indent=4)

def remove_content_from_har(path : str, log=print):
    """
    Remove the response content from given har file to reduce output size
    """
    log("📃 Removing response content from HAR-file")
    start_time = time.time()

    try:
        data = json.loads(open(path+".har", encoding='utf-8').read())

        if data.get("log") is None:
            log("❌ No content found")
            return

        for index, entry in enumerate(data["log"].get("entries")):
            if entry.get("response", {}).get("content", {}).get("text", "") == "":
                continue
            data["log"]["entries"][index]["response"]["content"]["text"] = ""

        with open(path + ".har", 'w', encoding="utf8") as fp:
            json.dump(data, fp, default=tuple, sort_keys=False, indent=2)

        duration = time.time() - start_time

        log(f"📃 Successfully removed response content from HAR-file in {duration:0.1f}s")

    except Exception as e:
        log(f"❌ Error removing response content: {e}")

def create_url_log_file(url : str, path : str):
    """
    Initialize log file for given url.
    """
    with open(path, 'w', encoding='utf-8') as fp:
        fp.write(f"ℹ️ Log file for {url} ℹ️\n\n")

OUTPUT_SITE_FILENAMES = [
    "_successful_sites.txt",
    "_failed_navigations_sites.txt",
    "_failed_crawl_sites.txt",
    "_timed_out_sites.txt"
    ]

def create_empty_file(file_path : str):
    """Initialize an empty file if it does not exist."""
    with open(file_path, 'w', encoding='utf-8') as fp:
        pass

def create_appended_site_files(output_path : str):
    """
    Initialize file to store successful and failed sites of the crawl.
    """
    for filename in OUTPUT_SITE_FILENAMES:
        create_empty_file(join(output_path, filename))

def read_urls_from_site_files(file_path : str):
    urls = set()
    for line in open(file_path, encoding="utf-8").read().splitlines():
        # Remove commented and empty lines
        if not line.startswith("#") and not line.strip() == '':
            urls.add(line.strip().lower())
    return urls

def read_appended_site_files(output_path : str):
    """
    Initialize file to store successful and failed sites of the crawl.
    """
    urls = set()
    for file_name in OUTPUT_SITE_FILENAMES:
        file_path = join(output_path, file_name)
        urls.update(read_urls_from_site_files(file_path))

    return urls


def append_to_sites_file(output_path : str, site : str, site_type : str):
    """
    Append to correct site file.
    """
    match site_type:
        case "success":
            append_to_file(join(output_path, "_successful_sites.txt"), site)
        case "navigation":
            append_to_file(join(output_path, "_failed_navigations_sites.txt"), site)
        case "crawl":
            append_to_file(join(output_path, "_failed_crawl_sites.txt"), site)
        case "timeout":
            append_to_file(join(output_path, "_timed_out_sites.txt"), site)
        case _:
            raise ValueError(f"Unknown site type for appending to site files! {site_type}")

def append_to_file(path : str, data: str):
    """Append data to a file."""
    with open(path, 'a', encoding='utf-8') as fp:
        fp.write(f"{data}\n")

if __name__ == "__main__":
    args = setup_arg_parser()
    print(args)
