import os
import json
import random
import requests
import base64
from slack_sdk import WebClient
from datetime import datetime

SLACK_TOKEN = os.environ['SLACK_TOKEN']
CHANNEL_ID = os.environ['CHANNEL_ID']
GITHUB_TOKEN = os.environ['TOKEN_GITHUB']
REPO = "dayoung-leferi/slack-lunch-bot"  # 본인 저장소명 확인!

client = WebClient(token=SLACK_TOKEN)

def get_week_number():
    """현재 주 번호"""
    return datetime.now().strftime("%Y_W%U")

def load_winners_from_github():
    """GitHub에서 당첨자 파일 읽기"""
    try:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
        }
        
        response = requests.get(
            f'https://api.github.com/repos/{REPO}/contents/winners.json',
            headers=headers
        )
        
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            data = json.loads(content)
            print(f"기존 당첨자 데이터 로드: {data}")
            return data
        else:
            print("winners.json 파일 없음, 새로 생성")
            return {"week": get_week_number(), "winners": []}
    except Exception as e:
        print(f"GitHub 로드 에러: {e}")
        return {"week": get_week_number(), "winners": []}

def save_winner_to_github(winner_id):
    """GitHub에 당첨자 저장"""
    # 1. 현재 데이터 가져오기
    data = load_winners_from_github()
    current_week = get_week_number()
    
    # 2. 주가 바뀌었으면 초기화
    if data.get("week") != current_week:
        data = {"week": current_week, "winners": []}
    
    # 3. 당첨자 추가
    data["winners"].append(winner_id)
    
    # 4. GitHub에 저장
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
    }
    
    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    
    # 5. 파일이 있는지 확인 (SHA 필요)
    sha = None
    try:
        response = requests.get(
            f'https://api.github.com/repos/{REPO}/contents/winners.json',
            headers=headers
        )
        if response.status_code == 200:
            sha = response.json()['sha']
    except:
        pass
    
    # 6. 파일 생성 또는 업데이트
    payload = {
        "message": f"Update winners - {datetime.now().strftime('%Y-%m-%d')} 당첨자: {winner_id}",
        "content": content,
        "branch": "main"
    }
    
    if sha:
        payload["sha"] = sha
    
    response = requests.put(
        f'https://api.github.com/repos/{REPO}/contents/winners.json',
        headers=headers,
        json=payload
    )
    
    if response.status_code in [200, 201]:
        print(f"당첨자 저장 성공: {winner_id}")
    else:
        print(f"저장 실패: {response.status_code} - {response.text}")

def draw_lottery():
    """11:00 실행 - 자동 추첨"""
    
    # GitHub에서 메시지 ID 읽기 (수정된 부분!)
    message_ts = load_message_id_from_github()
    
    if not message_ts:
        # 백업: 로컬 파일 시도
        try:
            with open('/tmp/message_ts.txt', 'r') as f:
                message_ts = f.read().strip()
                print(f"로컬 파일에서 찾음: {message_ts}")
        except:
            print("오늘 메시지를 찾을 수 없습니다")
            return
    
    # 1. 이모지 반응한 사용자 가져오기
    excluded_users = set()
    try:
        reactions = client.reactions_get(
            channel=CHANNEL_ID,
            timestamp=message_ts
        )
        
        if 'reactions' in reactions['message']:
            for reaction in reactions['message']['reactions']:
                if reaction['name'] in ['x', 'no_entry_sign', 'hand']:
                    excluded_users.update(reaction['users'])
    except:
        pass
    
    # 2. 채널 멤버 가져오기
    members = client.conversations_members(channel=CHANNEL_ID)['members']
    members = [m for m in members if m.startswith('U')]
    
    # 3. 이번 주 당첨자 가져오기 (GitHub에서)
    winners_data = load_winners_from_github()
    weekly_winners = []
    
    if winners_data.get('week') == get_week_number():
        weekly_winners = winners_data.get('winners', [])
        print(f"이번 주 기존 당첨자: {weekly_winners}")
    
    # 4. 제외 대상 합치기
    excluded_users.update(weekly_winners)
    print(f"제외 대상: {excluded_users}")
    
    # 5. 추첨 가능한 사람 필터링
    eligible = [m for m in members if m not in excluded_users]
    print(f"추첨 가능: {len(eligible)}명")
    
    if eligible:
        winner = random.choice(eligible)
        
        # GitHub에 저장
        save_winner_to_github(winner)
        
        # 원본 메시지 텍스트
        original_text = "🍽️ 오늘의 점심 당번 추첨을 시작합니다!\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요."
        
        # 당첨자 정보 추가
        divider = "═" * 24
        winner_text = f"""
    
    {divider}
    🎉 당첨자: <@{winner}>님
    
    📍 댓글에 가게 2곳을 올려주세요!
    👍 다른 분들은 댓글에 이모지(1️⃣,2️⃣)로 투표해주세요!
    {divider}"""
        
        # 메시지 수정
        client.chat_update(
            channel=CHANNEL_ID,
            ts=message_ts,
            text=original_text + winner_text
        )
        
        print(f"당첨자: {winner}")
        
    else:
        # 당첨 가능한 사람 없을 때
        original_text = "🍽️ 오늘의 점심 당번 추첨을 시작합니다!\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요."
        
        divider = "─" * 24
        no_winner_text = f"""
    
    {divider}
    😅 오늘은 선택 가능한 사람이 없네요!
    (이번 주 이미 {len(weekly_winners)}명 당첨)
    {divider}"""
        
        client.chat_update(
            channel=CHANNEL_ID,
            ts=message_ts,
            text=original_text + no_winner_text
        )

def load_message_id_from_github():
    """GitHub에서 오늘 메시지 ID 읽기"""
    try:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
        }
        
        response = requests.get(
            f'https://api.github.com/repos/{REPO}/contents/today_message.json',
            headers=headers
        )
        
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            data = json.loads(content)
            
            # 오늘 날짜 확인
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get('date') == today:
                print(f"GitHub에서 메시지 ID 찾음: {data['message_ts']}")
                return data['message_ts']
            else:
                print("저장된 메시지가 오늘 것이 아님")
                return None
        else:
            print("today_message.json 파일 없음")
            return None
    except Exception as e:
        print(f"GitHub에서 메시지 ID 로드 실패: {e}")
        return None

if __name__ == "__main__":
    draw_lottery()
