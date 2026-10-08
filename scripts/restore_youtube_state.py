"""Restore only validated receipt JSONs, fail closed on download errors."""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def main():
    repo, branch = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_REF_NAME']
    page = 1
    while True:
        result = subprocess.check_output(['gh', 'api',
            f'repos/{repo}/actions/artifacts?name=bong-youtube-state&per_page=100&page={page}'])
        artifacts = json.loads(result)['artifacts']
        for item in artifacts:
            if item['expired'] or item.get('workflow_run', {}).get('head_branch') != branch:
                continue
            archive = subprocess.check_output(['gh', 'api',
                f"repos/{repo}/actions/artifacts/{item['id']}/zip"])
            destination = Path('data/youtube')
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                for info in z.infolist():
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', info.filename):
                        raise ValueError('Unexpected state entry')
                    if info.file_size > 1000000 or not isinstance(json.loads(z.read(info)), dict):
                        raise ValueError('Invalid state entry')
                destination.mkdir(parents=True, exist_ok=True)
                z.extractall(destination)
            print('영상 요약 발송 상태 복원 완료')
            return
        if len(artifacts) < 100:
            print('영상 요약 초기 실행')
            return
        page += 1


if __name__ == '__main__':
    main()
