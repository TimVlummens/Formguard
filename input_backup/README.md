Here are brief descriptions of the files in this folder:
- _convert_csv_to_txt.ipynb: Jupyter notebook script that takes a .csv file containing the CRUX ranking as input and outputs the top X sites from that list as .txt file which can be used as input list for the crawler
- _convert_generate_list.ipynb: Jupyter notebook script that takes a .csv file containing the CRUX ranking as input and outputs a list sampled from that CRUX list as .txt file which can be used as input list for the crawler. The sampling randomly takes a specified number of sites from the top 1k, 1k-10k and 10k-100k ranges.
- sample.ipynb: Jupyter notebook script that samples the list of donation pages found in donation_pages.json.


- lists
    - list_compare_1k.txt: Sampled from the CRUX list (10th of July 2024). We used this list to compare the accuracy of the original and simplified models: https://github.com/TimVlummens/leak-detect_python_port/issues/7
    - list_test_100.txt: List of 100 sites used to test the robustness of the crawler on a smaller scale.
    - list_codegen_login_241002.txt: List of 60 sites created using _convert_generate_list.ipynb with 20 sites from each range. This list was used to generate the codegen files to test login navigation.
    - list_codegen_donate.txt: List of 30 sites used to generate the codegen files to test payment navigation
    - list_50k: List with the top 50k sites sampled from the CRUX List (9th of October 2024)
    - list_50k-100k: List with the top 100k sites, excluding the top 50k sites, sampled from the CRUX List (9th of October 2024)

- current_240710.csv.gz: The compressed raw dowload from the CRUX list (Version of 10th of July 2024) (https://github.com/zakird/crux-top-lists/tree/main/data/global)
- current_241009.csv.gz: The compressed raw dowload from the CRUX list (Version of 9th of October 2024) (https://github.com/zakird/crux-top-lists/tree/main/data/global)
- donation_pages.json: list of 3081 sites with a high likelyhood of being donation pages
