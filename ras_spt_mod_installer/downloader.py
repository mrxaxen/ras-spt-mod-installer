from ast import mod
import json
import os
from typing import Dict
import gdown
import traceback
import wget
import zipfile
import py7zr

from enum import Enum
from pathlib import Path
from collections import defaultdict
from pydantic import BaseModel, TypeAdapter


# NEW -> DOWNLOAD_FAILED/SUCCESS -> EXTRACT_FAILED/SUCCESS Can be REMOVED at any point
class RASDownloadStatus(Enum):
    NEW = "NEW"
    REMOVED = "REMOVED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    DOWNLOAD_SUCCESS = "DOWNLOAD_SUCCESS"
    EXTRACT_FAILED = "EXTRACT_FAILED"
    EXTRACT_SUCCESS = "OK"


class ModEntry(BaseModel):

    status: RASDownloadStatus = RASDownloadStatus.NEW
    file_path: str = ''
    member_files: list[str] = list()
    url: str


class RASDownloader:

    def __init__(self, download_folder: str, mods_file: str, progress_file: str) -> None:
        self.mod_install_progress: Dict[str, ModEntry] = dict()
        self.download_folder = download_folder
        self.mod_install_progress_file = progress_file
        self.mods_to_remove: list[str]
        self.__adapter = TypeAdapter(Dict[str, ModEntry])
        self.__taboo_paths = ['BepInEx/plugins/', 'user/mods/']
        requested_mods: dict

        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

        if os.path.exists(self.mod_install_progress_file):
            with open(self.mod_install_progress_file, 'rb') as file:
                file_content = file.read()
                self.mod_install_progress = self.__adapter.validate_json(file_content)

        if os.path.exists(mods_file):
            with open(mods_file, 'r') as file:
                requested_mods = json.load(file)

            self.mods_to_remove = [k for k, _ in self.mod_install_progress.items()]
            for mod_name, url in requested_mods.items():
                if mod_name in self.mods_to_remove:
                    self.mods_to_remove.remove(mod_name)
                if mod_name not in self.mod_install_progress:
                    self.mod_install_progress[mod_name] = ModEntry(url=url)
        else:
            raise FileNotFoundError(
                f'Mod enumeration file: {mods_file} not found! Please create a list of mods that you want to use!')

    def __write_progress(self):
        with open(self.mod_install_progress_file, 'wb') as file:
            content = self.__adapter.dump_json(self.mod_install_progress)
            file.write(content)

    # TODO: Swap out WGET, to a faster solution
    def download(self):
        print('Downloading mods..')
        for name, mod_entry in self.mod_install_progress.items():
            file_path = ''
            download_status = RASDownloadStatus.DOWNLOAD_FAILED
            download_condition = any([
                mod_entry.status == RASDownloadStatus.DOWNLOAD_FAILED,
                mod_entry.status == RASDownloadStatus.NEW,
            ])

            if download_condition:
                try:
                    print(f"\nDownloading: {mod_entry.url.split('/')[-1]}")
                    if "drive.google.com" in mod_entry.url:
                        file_path = gdown.download(
                            url=mod_entry.url, output=self.download_folder, fuzzy=True)
                    else:
                        file_path = wget.download(url=mod_entry.url, out=self.download_folder)
                    download_status = RASDownloadStatus.DOWNLOAD_SUCCESS
                except Exception:
                    traceback.print_exc()

                mod_entry.status = download_status
                mod_entry.file_path = file_path

        self.__write_progress()

    def extract(self):
        print('\nExtracting mods..')
        for name, mod_entry in self.mod_install_progress.items():
            extract_condition = any([
                mod_entry.status == RASDownloadStatus.EXTRACT_FAILED,
                mod_entry.status == RASDownloadStatus.DOWNLOAD_SUCCESS,
            ])
            if extract_condition:
                try:
                    if ".zip" in mod_entry.file_path:
                        with zipfile.ZipFile(file=mod_entry.file_path, mode='r') as file:
                            mod_entry.member_files = file.namelist()
                            file.extractall(".")
                    else:
                        with py7zr.SevenZipFile(file=mod_entry.file_path, mode='r') as file:
                            mod_entry.member_files = file.namelist()
                            file.extractall(".")

                    mod_entry.status = RASDownloadStatus.EXTRACT_SUCCESS
                except Exception:
                    traceback.print_exc()
                    mod_entry.status = RASDownloadStatus.EXTRACT_FAILED

        self.__write_progress()

    # TODO: Finish
    def remove(self):
        print('Removing mods..')
        for mod_name in self.mods_to_remove:
            print(f'Removing {mod_name}')
            mod_entry = self.mod_install_progress[mod_name]

            try:
                mod_directory_path = None
                member_files = mod_entry.member_files.copy()
                member_files.reverse()
                for path in member_files:
                    if path not in self.__taboo_paths:
                        print(f'Removing: {path}')
                        if os.path.exists(path):
                            if os.path.isdir(path):
                                os.rmdir(path)

                            if os.path.isfile(path):
                                os.remove(path)

                    if 'user/mods/' in path:
                        mod_directory_name = path.split('user/mods/')[1].split('/')[0]
                        mod_directory_path = f'user/mods/{mod_directory_name}'

                if mod_directory_path is not None and os.path.exists(mod_directory_path):
                    print(f'Removing: {mod_directory_path}')
                    os.rmdir(mod_directory_path)

                if os.path.exists(mod_entry.file_path):
                    print(f'Removing: {mod_entry.file_path}')
                    os.remove(mod_entry.file_path)

                self.mod_install_progress.pop(mod_name)
                print(f'Successfully removed {mod_name}')
            except Exception:
                traceback.print_exc()

    def run(self):
        self.remove()
        self.download()
        self.extract()
