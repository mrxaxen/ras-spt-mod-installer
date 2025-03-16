from sys import dont_write_bytecode
import wget
import json
import gdown
import os
import traceback
import zipfile
import py7zr

from collections import defaultdict
from downloader import RASDownloader


DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
DOWNLOAD_SUCCESS = "DOWNLOAD_SUCCESS"
EXTRACT_FAILED = "EXTRACT_FAILED"
EXTRACT_SUCCESS = "OK"

progress = defaultdict(lambda: [None, None])
download_folder = './mod_packages/'
mods_file = 'mods.json'
progress_file = 'modding_progress.json'


def main():
    downloader = RASDownloader(
        download_folder='./ras_mod_packages',
        mods_file='ras_mods.json',
        progress_file='ras_modding_progress.json'
    )

    downloader.download()
    downloader.extract()


if __name__ == '__main__':
    main()
