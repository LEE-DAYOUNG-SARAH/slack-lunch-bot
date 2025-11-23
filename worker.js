/**
 * Cloudflare Workers 버전
 * 
 * 사용법:
 * 1. Cloudflare Workers 대시보드에서 새 Worker 생성
 * 2. 이 코드 복사 붙여넣기
 * 3. 환경변수 설정: SLACK_TOKEN, CHANNEL_ID
 * 4. KV Storage 생성 및 바인딩: LUNCH_KV
 * 5. Triggers에서 Cron 설정:
 *    - 0 1 * * 1-5 (한국시간 10시)
 *    - 0 2 * * 1-5 (한국시간 11시)
 */
export default {
  async scheduled(event, env, ctx) {
    const kstTime = new Date(new Date().toLocaleString("en-US", {timeZone: "Asia/Seoul"}));
    const hour = kstTime.getHours();
    const day = kstTime.getDay();
    
    // 주말 제외 (0=일, 6=토)
    if (day === 0 || day === 6) return;
    
    if (hour === 10) {
      await this.startLottery(env);
    } else if (hour === 11) {
      await this.drawLottery(env);
    }
  },

  async startLottery(env) {
    const response = await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.SLACK_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: env.CHANNEL_ID,
        text: '🍽️ 오늘의 점심 당번 추첨을 시작합니다! <!here>\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요.',
      }),
    });
    
    const data = await response.json();
    
    // 메시지 ID를 KV에 저장 (11시에 사용)
    if (data.ok) {
      await env.LUNCH_KV.put('today_message', data.ts);
      console.log('Message sent:', data.ts);
    }
  },

  async drawLottery(env) {
    // 저장된 메시지 ID 가져오기
    const messageTs = await env.LUNCH_KV.get('today_message');
    if (!messageTs) {
      console.log('No message found for today');
      return;
    }
    
    // 리액션 확인 (불참자)
    const reactions = await fetch(`https://slack.com/api/reactions.get?channel=${env.CHANNEL_ID}&timestamp=${messageTs}`, {
      headers: {
        'Authorization': `Bearer ${env.SLACK_TOKEN}`,
      },
    });
    
    const reactData = await reactions.json();
    let excluded = [];
    
    if (reactData.ok && reactData.message.reactions) {
      reactData.message.reactions.forEach(reaction => {
        if (reaction.name === 'x' || reaction.name === 'no_entry_sign') {
          excluded = excluded.concat(reaction.users);
        }
      });
    }
    
    // 이번 주 당첨자 확인
    const weekNumber = this.getWeekNumber();
    const weekKey = `week_${weekNumber}_winners`;
    const weeklyWinnersData = await env.LUNCH_KV.get(weekKey);
    const weeklyWinners = weeklyWinnersData ? JSON.parse(weeklyWinnersData) : [];
    
    // 주간 당첨자도 제외 목록에 추가
    excluded = excluded.concat(weeklyWinners);
    console.log(`제외 대상: ${excluded.length}명 (불참: ${excluded.length - weeklyWinners.length}, 기당첨: ${weeklyWinners.length})`);
    
    // 채널 멤버 가져오기
    const members = await fetch(`https://slack.com/api/conversations.members?channel=${env.CHANNEL_ID}`, {
      headers: {
        'Authorization': `Bearer ${env.SLACK_TOKEN}`,
      },
    });
    
    const memberData = await members.json();

    // 점심봇 제외하고 필터링
    const LUNCH_BOT_ID = 'U09RAUD8QR3';
    const eligible = memberData.members.filter(m => 
      m !== LUNCH_BOT_ID && !excluded.includes(m)
    );
    
    console.log(`추첨 가능: ${eligible.length}명`);
    
    if (eligible.length === 0) {
      // 추첨 가능한 사람이 없을 때
      await fetch('https://slack.com/api/chat.update', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.SLACK_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          channel: env.CHANNEL_ID,
          ts: messageTs,
          text: `🍽️ 오늘의 점심 당번 추첨을 시작합니다! <!here>\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요.\n\n😅 오늘은 선택 가능한 사람이 없네요!\n(이번 주 이미 ${weeklyWinners.length}명 당첨)`,
        }),
      });
      return;
    }
    
    // 랜덤 선택
    const winner = eligible[Math.floor(Math.random() * eligible.length)];
    
    // 당첨자를 주간 목록에 저장
    weeklyWinners.push(winner);
    await env.LUNCH_KV.put(weekKey, JSON.stringify(weeklyWinners));
    
    // 오늘 날짜도 저장 (디버깅용)
    const today = new Date().toLocaleDateString('ko-KR', {timeZone: 'Asia/Seoul'});
    await env.LUNCH_KV.put(`winner_${today}`, winner);
    
    // 결과 발표
    await fetch('https://slack.com/api/chat.update', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.SLACK_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: env.CHANNEL_ID,
        ts: messageTs,
        text: `🍽️ 오늘의 점심 당번 추첨을 시작합니다! <!here>\n불참하실 분은 11시까지 ❌ 이모지를 달아주세요.\n\n🎉 당첨자: <@${winner}>님!\n\n📍 댓글에 가게 2곳을 올려주세요!\n👍 다른 분들은 댓글에 이모지(1️⃣,2️⃣)로 투표해주세요!`,
      }),
    });

    // 댓글로 당첨자 태그 추가
    await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.SLACK_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: env.CHANNEL_ID,
        thread_ts: messageTs,  // 스레드로 달기
        text: `<@${winner}> 님, 오늘의 점심 당번입니다! 11시 30분까지 가게 2곳을 댓글로 올려주세요 🍽️\n(댓글 다실 때 <!here> 멘션 한 번만 부탁드려요!)`,
      }),
    });
    
    console.log(`당첨자: ${winner} (주간 ${weeklyWinners.length}번째)`);
  },
  
  // 주 번호 계산 함수 (년도별 주차)
  getWeekNumber() {
    const now = new Date(new Date().toLocaleString("en-US", {timeZone: "Asia/Seoul"}));
    const year = now.getFullYear();
    const onejan = new Date(year, 0, 1);
    const weekNumber = Math.ceil((((now.getTime() - onejan.getTime()) / 86400000) + onejan.getDay() + 1) / 7);
    return `${year}_W${weekNumber}`;
  }
};
