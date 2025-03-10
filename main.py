import wget
import json
import gdown
import os
import traceback
import zipfile
import py7zr

from collections import defaultdict


DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
DOWNLOAD_SUCCESS = "DOWNLOAD_SUCCESS"
EXTRACT_FAILED = "EXTRACT_FAILED"
EXTRACT_SUCCESS = "OK"

progress = defaultdict(lambda: [None, None])
download_folder = './mod_packages/'
mods_file = 'mods.json'
progress_file = 'modding_progress.json'


def download():
    mod_urls = None

    with open(mods_file, 'r+') as file:
        mod_urls = json.load(file)

    if not os.path.exists(download_folder):
        os.mkdir(download_folder)

    for name, url in mod_urls.items():
        if name in progress and progress[name][0] == DOWNLOAD_FAILED or name not in progress:
            try:
                print(f"\nDownloading: {url.split('/')[-1]}")
                if "drive.google.com" in url:
                    file_path = gdown.download(url=url, output=download_folder, fuzzy=True)
                else:
                    file_path = wget.download(url=url, out=download_folder)
            except Exception:
                traceback.print_exc()
                file_path = ""
                progress[name] = [DOWNLOAD_FAILED, file_path]

            progress[name] = [DOWNLOAD_SUCCESS, file_path]


def extract():
    for name, val in progress.items():
        if progress[name][0] == EXTRACT_FAILED or progress[name][0] == DOWNLOAD_SUCCESS:
            filename = val[1]
            assert filename is not None

            try:
                if ".zip" in filename:
                    with zipfile.ZipFile(file=filename, mode='r') as file:
                        file.extractall(".")
                else:
                    with py7zr.SevenZipFile(file=filename, mode='r') as file:
                        file.extractall(".")

                progress[name][0] = EXTRACT_SUCCESS
            except Exception:
                progress[name][0] = EXTRACT_FAILED

    with open(progress_file, 'w+') as file:
        file.write(json.dumps(progress))


if os.path.exists(progress_file):
    with open(progress_file) as file:
        progress = json.load(file)

download()
extract()
