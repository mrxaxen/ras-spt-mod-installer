import traceback
import git
import os
import sys
import wget
import subprocess

from shutil import which
from downloader import RASDownloader


# TODO: git pull
# TODO: launch downloader
# TODO: launch SPT launcher
class RASLauncher:

    def __init__(self) -> None:
        download_folder = 'ras_resources/mod_packages/'
        mods_file = 'ras_mods.json'
        progress_file = 'ras_modding_progress.json'
        self.downloader = RASDownloader(
            download_folder=download_folder,
            mods_file=mods_file,
            progress_file=progress_file,
        )
        self.git_folder = 'ras_resources/git/'
        self.git_url = 'https://github.com/git-for-windows/git/releases/download/v2.48.1.windows.1/Git-2.48.1-64-bit.exe'
        self.git_repo: git.Repo

    def check_git_availability(self):
        print('Checking system git availability..')
        if not which('git'):
            print('Downloading and installing git..')
            if not os.path.exists(self.git_folder):
                os.mkdir(self.git_folder)

            git_installer_path = None
            try:
                git_installer_path = wget.download(
                    self.git_url, out=f'{self.git_folder}/git_installer.exe')

                install_cmd = f'start {git_installer_path}'.split()
                process = subprocess.run(install_cmd, check=True)
                self.git = git.Git()
                version = [str(v) for v in self.git.version_info]
                print(f'Installed git version: {".".join(version)}')
            except subprocess.CalledProcessError:
                print(
                    f'Git installation failed. The installer is located at: {git_installer_path}, please attempt it manually.')
                traceback.print_exc()
                sys.exit(1)
            except Exception:
                print('Git installer download failed')
                traceback.print_exc()
                sys.exit(1)
        else:
            self.git = git.Git()
            print('Git is available!')

    def check_if_repo_exists(self):
        print('Setting up git repository..')
        if not git.Repo.active_branch == 'master':
            self.git_repo = git.Repo.init()
            origin = git.Remote.add(
                repo=self.git_repo,
                name='origin',
                url='https://github.com/mrxaxen/spt-coop-config-3.10.git'
            )
            origin.fetch()
            self.git_repo.create_head("master", origin.refs.master)
            self.git_repo.heads.master.set_tracking_branch(origin.refs.master)
            self.git_repo.head.reset(commit='FETCH_HEAD', index=True, working_tree=True)
        else:
            self.git_repo = git.Repo()

    def pull_config_changes(self):
        self.check_git_availability()
        self.check_if_repo_exists()

        self.git_repo.remote().pull()

    def launch_spt(self):
        print('Launching SPT.. Have fun!')
        cmd = 'start SPT.Launcher.exe'.split()
        process = subprocess.Popen(cmd, start_new_session=True)

    def run(self):
        self.pull_config_changes()
        self.downloader.run()
        self.launch_spt()


def main():
    launcher = RASLauncher()
    launcher.run()


if __name__ == '__main__':
    main()
