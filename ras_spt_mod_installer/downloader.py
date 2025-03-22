import asyncio
import json
import math
import os
import traceback
import wget
import zipfile
import py7zr
import httpx
import logging
import sys

from alive_progress import alive_bar
from io import UnsupportedOperation
from enum import Enum
from typing import Dict, Tuple
from pydantic import BaseModel, TypeAdapter
from httpx import Response


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

    def __init__(self, download_folder: str, mods_file: str, progress_file: str, multipart_chunck_size: int, num_of_connections: int) -> None:
        self.mod_install_progress: Dict[str, ModEntry] = dict()
        self.download_folder = download_folder
        self.mod_install_progress_file = progress_file
        self.mods_to_remove: list[str]
        self.__mods_file = mods_file
        self.__adapter = TypeAdapter(Dict[str, ModEntry])
        self.__taboo_paths = ['BepInEx/plugins/', 'user/mods/']
        self.__chunck_size = multipart_chunck_size
        self.__num_of_connections = num_of_connections
        requested_mods: dict

        self.__logger = logging.getLogger(RASDownloader.__name__)

        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

        if os.path.exists(self.mod_install_progress_file):
            with open(self.mod_install_progress_file, 'rb') as file:
                file_content = file.read()
                self.mod_install_progress = self.__adapter.validate_json(file_content)

    def __check_mods_file_exists(self):
        if os.path.exists(self.__mods_file):
            with open(self.__mods_file, 'r') as file:
                requested_mods = json.load(file)

            self.mods_to_remove = [k for k, _ in self.mod_install_progress.items()]
            for mod_name, url in requested_mods.items():
                if mod_name in self.mods_to_remove:
                    self.mods_to_remove.remove(mod_name)
                if mod_name not in self.mod_install_progress:
                    self.mod_install_progress[mod_name] = ModEntry(url=url)
        else:
            raise FileNotFoundError(
                f'Mod enumeration file: {self.__mods_file} not found! Please create a list of mods that you want to use!')

    def __write_progress(self):
        with open(self.mod_install_progress_file, 'wb') as file:
            content = self.__adapter.dump_json(self.mod_install_progress)
            file.write(content)

    def download(self):
        client = httpx.Client()
        for name, mod_entry in self.mod_install_progress.items():
            response = client.request(method='HEAD', url=mod_entry.url)
            if 'location' in response.headers:
                mod_entry.url = response.headers['location']
                response = client.request(method='HEAD', url=mod_entry.url)

            response.raise_for_status()
            mod_name = response.headers['content-disposition'].split('filename=')[1].split('.')[0]

            try:
                file_path: str
                download_condition = any([
                    mod_entry.status == RASDownloadStatus.DOWNLOAD_FAILED,
                    mod_entry.status == RASDownloadStatus.NEW, ])

                if download_condition:
                    self.__logger.info(f"Downloading: {mod_name}")
                    if 'accept-ranges' in response.headers and int(response.headers['content-length']) > self.__chunck_size:
                        file_path = self.__download_multi_thread(name, mod_entry, response)
                    else:
                        file_path = self.__download_single_thread(name, mod_entry)
                    mod_entry.file_path = file_path
                    mod_entry.status = RASDownloadStatus.DOWNLOAD_SUCCESS
            except Exception:
                mod_entry.status = RASDownloadStatus.DOWNLOAD_FAILED
                self.__logger.error(traceback.format_exc())

        self.__write_progress()

    def __download_multi_thread(self, name: str, mod_entry: ModEntry, response: Response) -> str:
        content_length = int(response.headers['content-length'])

        # Range selection
        start = 0
        ranges = []
        for i in range(content_length // self.__chunck_size):
            ranges.append((start + i * self.__chunck_size,
                          self.__chunck_size + i * self.__chunck_size - 1))

        if ranges[-1][1] < content_length:
            # That +1 took me 1,5 hours to figure out..
            ranges.append((ranges[-1][1]+1, content_length))

        self.__logger.debug(f'Frame byte ranges: {ranges}')

        async def download_chunk(url: str, rng: Tuple[int, int], idx: int):
            try:
                client = httpx.AsyncClient()
                headers = {
                    'range': f'bytes={rng[0]}-{rng[1]}'
                }
                response = await client.request(method='GET', url=url, headers=headers)
                response.raise_for_status()
                return idx, response.content
            except Exception as e:
                self.__logger.debug(
                    f'Exception occured when downloading frame {idx}: {traceback.format_exc()}')
                return idx, e

        jobs = [
            download_chunk(url=mod_entry.url, rng=rng, idx=idx) for idx, rng in enumerate(ranges)
        ]
        chunk_progress = [b'-1' for e in jobs]

        tries = 0
        max_tries = int(content_length // self.__chunck_size * 1.5)
        with alive_bar(math.ceil(content_length // self.__chunck_size / self.__num_of_connections)) as bar:
            while len(jobs) > 0 and tries < max_tries:
                current_jobs = []
                for i in range(self.__num_of_connections):
                    try:
                        current_jobs.append(jobs.pop())
                    except IndexError:
                        self.__logger.debug('End of jobs array reached.')
                        break

                async def download_routine():
                    return await asyncio.gather(*current_jobs, return_exceptions=False)
                results = asyncio.run(download_routine(), debug=True)

                tries += 1
                for idx, result in results:
                    if isinstance(result, Exception):
                        jobs.append(download_chunk(url=mod_entry.url, rng=ranges[idx], idx=idx))
                        if tries > max_tries:
                            raise Exception(
                                f'Multipart download failed for entry. Too many retries. Err: {result}')
                    else:
                        chunk_progress[idx] = result

                bar()

        filename = response.headers['content-disposition'].split('filename=')[1]
        file_path = os.path.join(self.download_folder, filename)
        assert b'-1' not in chunk_progress

        with open(file=file_path, mode='wb') as file:
            bytes_written = 0
            for entry in chunk_progress:
                bytes_written += file.write(entry)

            self.__logger.debug(f'Written: {bytes_written}, content length: {content_length}')
            assert bytes_written == content_length

        return os.path.normpath(file_path)

    def __download_single_thread(self, name: str, mod_entry: ModEntry) -> str:
        file_path = wget.download(url=mod_entry.url, out=self.download_folder)
        print('\n')
        return os.path.normpath(file_path)

    def extract(self):
        self.__logger.info('Extracting mods..')
        for name, mod_entry in self.mod_install_progress.items():
            self.__logger.info(f'Extracting mod: {name}')
            extract_condition = any([
                mod_entry.status == RASDownloadStatus.EXTRACT_FAILED,
                mod_entry.status == RASDownloadStatus.DOWNLOAD_SUCCESS,
            ])
            if extract_condition:
                try:
                    if zipfile.is_zipfile(mod_entry.file_path):
                        with zipfile.ZipFile(file=mod_entry.file_path, mode='r') as file:
                            mod_entry.member_files = file.namelist()
                            file.extractall(".")

                    elif py7zr.is_7zfile(mod_entry.file_path):
                        with py7zr.SevenZipFile(file=mod_entry.file_path, mode='r') as file:
                            mod_entry.member_files = file.namelist()
                            file.extractall(".")
                    else:
                        raise UnsupportedOperation('File format is not supported!')

                    mod_entry.status = RASDownloadStatus.EXTRACT_SUCCESS
                except Exception:
                    self.__logger.error(
                        f'An error occured while extracting files: {traceback.format_exc()}')
                    mod_entry.status = RASDownloadStatus.EXTRACT_FAILED

        self.__write_progress()

    def remove(self):
        self.__logger.info('Removing mods..')
        for mod_name in self.mods_to_remove:
            self.__logger.info(f'Removing {mod_name}')
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
                    self.__logger.debug(f'Removing: {mod_directory_path}')
                    os.rmdir(mod_directory_path)

                if os.path.exists(mod_entry.file_path):
                    self.__logger.debug(f'Removing: {mod_entry.file_path}')
                    os.remove(mod_entry.file_path)

                self.mod_install_progress.pop(mod_name)
                self.__logger.info(f'Successfully removed {mod_name}')
            except Exception:
                self.__logger.error(
                    f'An error occured while trying to remove mod {mod_name}: {traceback.format_exc()}')

    def print_status(self):
        print('\n')
        for mod_name, mod_entry in self.mod_install_progress.items():
            print(f'{mod_name}: Progress: {mod_entry.status.value}')

        print('\n')

    def run(self):
        self.__check_mods_file_exists()
        self.remove()
        self.download()
        self.extract()
        self.print_status()
