import traceback
import git
import os
import sys
import httpx
import wget
import subprocess
import logging
import zipfile

from git.exc import InvalidGitRepositoryError
from shutil import which
from downloader import RASDownloader


class RASLauncher:

    def __init__(self) -> None:
        download_folder = 'ras_resources/mod_packages/'
        mods_file = 'ras_mods.json'
        progress_file = 'ras_modding_progress.json'
        self.downloader = RASDownloader(
            download_folder=download_folder,
            mods_file=mods_file,
            progress_file=progress_file,
            multipart_chunck_size=50000000,
            num_of_connections=5
        )
        self.git_folder = 'ras_resources/git/'
        self.git_url = 'https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/MinGit-2.49.0-64-bit.zip'
        self.ras_mods_file_url = 'https://raw.githubusercontent.com/mrxaxen/spt-coop-config-3.10/refs/heads/master/ras_mods.json'
        self.git_repo: git.Repo

        self.__logger = logging.getLogger(RASLauncher.__name__)

    def check_git_availability(self):
        self.__logger.info('Checking system git availability..')
        if not which('git'):
            self.__logger.info('Downloading and installing git..')
            if not os.path.exists(self.git_folder):
                os.mkdir(self.git_folder)

            git_installer_path = None
            try:
                git_installer_path = wget.download(self.git_url, out=f'{self.git_folder}')

                if zipfile.is_zipfile(git_installer_path):
                    with zipfile.ZipFile(file=git_installer_path, mode='r') as file:
                        file.extractall(self.git_folder)

                os.environ['PATH'] += os.pathsep + os.path.join(self.git_folder, 'cmd')

                self.git = git.Git()
                version = [str(v) for v in self.git.version_info]
                self.__logger.info(f'Installed git version: {".".join(version)}')
            except subprocess.CalledProcessError:
                self.__logger.error(
                    f'Git install failed. The portable version is located at: {git_installer_path}, please attempt to add its cmd folder to PATH manually.')
                traceback.print_exc()
                sys.exit(1)
            except Exception:
                self.__logger.error('Git installer download failed')
                traceback.print_exc()
                sys.exit(1)
        else:
            self.git = git.Git()
            self.__logger.info('Git is available!')

    def check_if_repo_exists(self):
        self.__logger.info('Setting up git repository..')
        try:
            self.git_repo = git.Repo()
        except InvalidGitRepositoryError:
            self.git_repo = None

        if not self.git_repo:
            self.git_repo = git.Repo.init()
            origin = git.Remote.add(
                repo=self.git_repo,
                name='origin',
                url='https://github.com/mrxaxen/spt-coop-config-3.10.git'
            )
            origin.fetch()
            self.git_repo.create_head("master", origin.refs.master)
            self.git_repo.heads.master.set_tracking_branch(origin.refs.master)

    def apply_config_changes(self):

        self.git_repo.remote().fetch()
        self.git_repo.head.reset('FETCH_HEAD', index=True, working_tree=True)
        self.git.execute('git restore .'.split())  # TODO: Test this

    def launch_spt(self):
        files = os.listdir()
        launcher_path = ''
        for file in files:
            if 'SPT' in file and 'Launcher' in file:
                launcher_path = file

        if launcher_path:
            path = os.path.join(os.getcwd(), launcher_path)
            cmd = f'cmd /c start {path}'.split()
            process = subprocess.Popen(cmd, start_new_session=True)
            self.__logger.info('Launching SPT.. Have fun!')
        else:
            self.__logger.warning(
                'SPT Launcher not found! Please make sure you are running the RAS Launcher from the same directory!')

    def get_mods_file(self):
        client = httpx.Client()
        response = client.request(method='GET', url=self.ras_mods_file_url)
        response.raise_for_status()

        with open('ras_mods.json', 'wb') as file:
            file.write(response.content)

    def run(self):
        self.check_git_availability()
        self.check_if_repo_exists()
        self.get_mods_file()
        # self.downloader.run()
        self.apply_config_changes()
        self.launch_spt()


def exception_hook(type, value, traceback, oldhook=sys.excepthook):
    oldhook(type, value, traceback)
    print('Please make a screenshot of the error and send it to me! Github: @mrxaxen')
    input('Press RETURN to exit...')


def main():
    log_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)
    logging.getLogger().addHandler(log_handler)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler = logging.FileHandler('./ras_logging')
    logging.getLogger().addHandler(log_handler)

    logging.getLogger().setLevel(logging.INFO)

    sys.excepthook = exception_hook
    launcher = RASLauncher()
    launcher.run()
    input('Press RETURN to exit...')


if __name__ == '__main__':
    main()
