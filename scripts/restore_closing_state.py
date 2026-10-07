"""Restore the latest branch-specific state; a download error is fatal."""
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile


def gh(path):
    return subprocess.check_output(['gh', 'api', path])


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    branch = os.environ['GITHUB_REF_NAME']
    page = 1
    while True:
        data = json.loads(gh(f'repos/{repo}/actions/artifacts?name=bong-closing-state&per_page=100&page={page}'))
        for artifact in data['artifacts']:
            if artifact['expired'] or artifact.get('workflow_run', {}).get('head_branch') != branch:
                continue
            archive = gh(f"repos/{repo}/actions/artifacts/{artifact['id']}/zip")
            destination = Path('data/closing').resolve()
            destination.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                # Only data, never executable code, is restored.
                for info in z.infolist():
                    target = (destination / info.filename).resolve()
                    if not target.is_relative_to(destination) or (not info.is_dir() and target.suffix != '.json'):
                        raise ValueError('Unexpected artifact entry')
                z.extractall(destination)
            print('이전 스냅샷 및 발송 상태 복원 완료')
            return
        if len(data['artifacts']) < 100:
            print('초기 실행: 과거 6거래일 자동 수집 예정')
            return
        page += 1


if __name__ == '__main__':
    main()
