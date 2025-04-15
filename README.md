# Formguard

## Folder content
The src folder contains the code for Formguard's record-replay and crawler.
The codegens_recordings folder contains the 75 recordings used for the long-term robustness test, divided in a donation and login folder.
The notebooks folder contains the notebooks used for final analysis.
The input_backup folder contains the site lists used in the crawls.
The leak_detector folder contains the detector used to analyze the crawl results.

## Running the crawler
 
Run from src folder with either:
```
python crawler_main.py -create <path to config> # Create a default config file to specified path
```
or
```
python crawler_main.py -config <path to config> # Run crawl with specified config file
```

The config file contains the following options:
- url:  (str) url to visit for a single site crawl.
- list: (str) path to file containing list of urls to visit for multiple site crawl. Each line is a seperate site.

- headless:     (bool) option to run in headless (true) or headed mode (false).
- window_pos_x: (bool) x coordinate of the window for headed mode. (Can be placed of screen)
- window_pos_y: (bool) y coordinate of the window for headed mode. (Can be placed of screen)

- mode: (int)   0: full crawl
                1: fill input on a limited number of pages, specified by "amount" value
                2: only interact with the landing page
                3: record and replay an interaction
                4: replay an interaction
                5: compare the detection of fathom and the simplified model

- amount:             (int) number of pages to fill for mode 1
- cpu_slice:          (float) fraction of cores to use out of the maximum when crawling a list of sites
- crawl_max_duration: (int) maximum time in seconds of a single site visit before a timeout is triggered

- output_path: (str) folder where the output will be stored.
- record_full  (bool) wether or not to record additional data such as script information
- resume:      (bool) if true, will check the files at the output path and skip the already completed sites found there when running a new crawl.
- screenshot:  (bool) wether or not to take a screenshot before and after interacting with the cookie consent dialog.
- video:       (bool) wether or not to record the visit to the page as a video.

- pierce:         (bool) wether or not to force created shadow_roots to be accessible and open instead of closed.
- accept_cookies: (bool) wether to accept cookies or ignore them when automatically crawling.

- replay_path:        (str) path to the file/folder for replaying an interaction.
- record_with_firefox (bool) wether to record interactions with chrome (default) or firefox. Sometimes certain interactions are not picked up in chrome
- replay_multiple:    (bool) wether or not to replay mutliple files at once.
- wait_for_close:     (bool) wether or not to automatically close the window after completing the replay.
- clear_fields:       (bool) wether or not to clear the fields before starting to fill them.
