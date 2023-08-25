from github import Auth
from github import Github
from datetime import datetime
import os
import git

from aws_template_generate_file import GenerateFile

MAIN_BRANCH = 'main'


class HandleGithub:
    def __init__(self, token, repo_name, base_repo_name=None) -> None:
        self.token = token
        self.auth = Auth.Token(self.token)
        self.g = Github(auth=self.auth)
        self.repo = self.g.get_repo(repo_name)
        if base_repo_name is not None:
            self.base_repo = self.g.get_repo(base_repo_name)

    def update_file(self, file_name, branch, commit_title, update_content):
        file_on_github = self.repo.get_contents(file_name, branch)
        self.repo.update_file(file_on_github.path, commit_title, update_content, file_on_github.sha, branch)
        return file_on_github

    def send_pull_request_to_base_repo(self, pull_request_title, pull_request_comment, head_branch, base_branch):
        pr = self.base_repo.create_pull(title=pull_request_title, body=pull_request_comment, head=head_branch, base=base_branch)
        return pr
    
class HandleGit:
    def __init__(self) -> None:
        self.work_path = ""
        self.repo = None
        self.git = None

    def set_git_config(self, email, name):
        self.git.config('--global', 'user.email', email)
        self.git.config('--global', 'user.name', name)

    def get_repo(self, repo_url, save_path):
        if os.path.exists(save_path):
            self.repo = git.Repo(save_path)
        else:
            self.repo = git.Repo.clone_from(url=repo_url, to_path=save_path)
        self.git = self.repo.git
        self.work_path = save_path

    def switch_to_work_branch(self, branch):
        if self.git.branch().find(branch) == -1:
            self.git.checkout('-b', branch, "origin/" + MAIN_BRANCH)
        else:
            self.git.checkout(branch)

    def upload_to_remote_repo(self, mes) -> bool:
        if self.repo.is_dirty() is True:
            self.git.add('.')
            self.git.commit('-m', mes)
            self.git.push('origin', 'HEAD')
            return True
        else:
            return False

    def set_remote_repo(self, push_repo, fetch_repo):
        self.git.remote("set-url", "origin", fetch_repo)
        self.git.remote("set-url", "--push" ,"origin", push_repo)

    def sync_remote_repo(self):
        self.git.fetch()

    def rewrite_file(self, filename, content):
        with open(filename, 'w') as f:
            f.write(content)

if __name__ == '__main__':
    token = os.getenv('GITHUB_TK')
    push_url = os.getenv('GITHUB_PUSH_URL')
    fetch_url = os.getenv('GITHUB_FETCH_URL')
    repo = push_url[15:-4]
    base_repo = fetch_url[15:-4]
    user = repo.split('/')[0]
    base_user = base_repo.split('/')[0]
    print(repo, base_repo, user, base_user)
    native_path = './sonicwall-nsv-aws-cf-templates'
    git_config_user = os.getenv('GIT_CONFIG_USER')
    git_config_email = os.getenv('GIT_CONFIG_EMAIL')
    work_branch_prefix = os.getenv('WORK_BRANCH')
    work_branch = work_branch_prefix + datetime.today().strftime('%Y-%m-%d-%H-%M-%S')

    handleGithub = HandleGithub(token, repo, base_repo)
    handleGit = HandleGit()
    handleGit.get_repo(fetch_url, native_path)

    generateFile = GenerateFile()
    generateFile.generate_files()
    
    handleGit.set_git_config(git_config_email, git_config_user)
    handleGit.set_remote_repo(push_url, fetch_url)
    handleGit.sync_remote_repo()
    handleGit.switch_to_work_branch(work_branch)
    old_version = generateFile.generate_mapping_from_json("single-ami/cf-existing-vpc.template")
    msg = generateFile.cmp_versions(old_version)
    print(msg)
    handleGit.rewrite_file(os.path.join(native_path, "single-ami/cf-existing-vpc.template"), generateFile.CF_EXISTING_VPC_TEMPLATE)
    handleGit.rewrite_file(os.path.join(native_path, "single-ami/cf-new-vpc.template"), generateFile.CF_NEW_VPC_TEMPLATE)
    if handleGit.upload_to_remote_repo(msg) is True:
        pr = handleGithub.send_pull_request_to_base_repo("Update NSv AMI ID", msg, user + ":" + work_branch, MAIN_BRANCH)
        print(pr)
        pass
    else:
        print('No need to send pull request')
    
