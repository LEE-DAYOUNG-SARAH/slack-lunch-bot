import os
import json
import base64
import requests
from slack_sdk import WebClient
from datetime import datetime

SLACK_TOKEN = os.environ['SLACK_TOKEN']
CHANNEL_ID = os.environ['CHANNEL_ID']
GITHUB_TOKEN = os.environ.get('TOKEN_GITHUB', '')
REPO = "dayoung-leferi/slack-lunch-bot"

client = WebClient(token=SLACK_TOKEN)

def save_message_id_to_github(message_ts):
    """GitHub에 메시지 ID 저장"""
    if not GITHUB_TOKEN:
        print("GitHub 토큰 없음, 파일에만 저장")
        return
        
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
    }
    
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "message_ts": message_ts,
        "created_at": datetime.now().isoformat()
    }
    
    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    
    # 기존 파일 SHA 확인
    sha = None
    try:
        response = requests.get(
            f'https://api.github.com/repos/{REPO}/contents/today_message.json',
            headers=headers
        )
        if response.status_code == 200:
            sha = response.json()['sha']
    except:
        pass
    
    # 파일 생성 또는 업데이트
    payload = {
        "message": f"Save today's message ID - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content,
        "branch": "main"
    }
    
    if sha:
        payload["sha"] = sha
    
    response = requests.put(
        f'https://api.github.com/repos/{REPO}/contents/today_message.json',
        headers=headers,
        json=payload
    )
    
    if response.status_code in [200, 201]:
        print(f"메시지 ID 저장 성공: {message_ts}")
    else:
        print(f"저장 실패: {response.status_code}")

def start_lottery():
    """10:30 실행 - 추첨 시작 메시지"""
    result = client.chat_postMessage(
        channel=CHANNEL_ID,
        text="🍽️ 오늘의 점심 당번 추첨을 시작합니다!\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요."
    )
    
    message_ts = result['ts']
    
    # GitHub에 저장
    save_message_id_to_github(message_ts)
    
    # 로컬 파일에도 저장 (백업)
    with open('/tmp/message_ts.txt', 'w') as f:
        f.write(message_ts)
    
    print(f"추첨 시작! 메시지 ID: {message_ts}")

if __name__ == "__main__":
    start_lottery()
