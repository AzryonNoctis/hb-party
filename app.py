import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template_string, send_from_directory, session, flash, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'hb-party-secret')

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'birthday_data'
UPLOADS_DIR = BASE_DIR / 'uploads'
EVENTS_FILE = DATA_DIR / 'events.json'
AGORA_APP_ID = os.getenv('AGORA_APP_ID', '')
AGORA_TEMP_TOKEN = os.getenv('AGORA_TEMP_TOKEN', '')

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
if not EVENTS_FILE.exists():
    EVENTS_FILE.write_text('{}', encoding='utf-8')


def load_events():
    try:
        return json.loads(EVENTS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_events(events):
    EVENTS_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')


def now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def normalize(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def allowed_image(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def allowed_audio(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in {'mp3', 'wav', 'ogg', 'm4a'}


def get_event(event_id):
    return load_events().get(event_id)


def update_event(event_id, event):
    events = load_events()
    events[event_id] = event
    save_events(events)


def event_by_birthday_name(name):
    target = normalize(name)
    for event_id, ev in load_events().items():
        if normalize(ev['birthday_name']) == target:
            return event_id, ev
    return None, None


def role_of(event, person_name):
    n = normalize(person_name)
    if n == normalize(event['creator_name']):
        return 'creator'
    if n == normalize(event['birthday_name']):
        return 'birthday'
    return 'guest'


def find_participant(event, person_name):
    for p in event.get('participants', []):
        if normalize(p['name']) == normalize(person_name):
            return p
    return None


def participant_exists(event, person_name):
    return find_participant(event, person_name) is not None


def join_event(event_id, person_name):
    events = load_events()
    event = events[event_id]
    p = find_participant(event, person_name)
    if p:
        p['last_seen'] = now_iso()
    else:
        p = {
            'name': person_name.strip(),
            'role': role_of(event, person_name),
            'camera_ready': False,
            'joined_at': now_iso(),
            'last_seen': now_iso(),
        }
        event.setdefault('participants', []).append(p)
    events[event_id] = event
    save_events(events)
    return p

HOME_HTML = r'''<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>hb.party</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:Arial,sans-serif;color:#fff;background:radial-gradient(circle at 20% 20%, #7c2cbf 0%, rgba(124,44,191,.18) 18%, transparent 35%),radial-gradient(circle at 80% 10%, #ff5ea8 0%, rgba(255,94,168,.16) 18%, transparent 35%),linear-gradient(160deg,#0b0612 0%,#1a0f2b 48%,#12081d 100%);display:flex;align-items:center;justify-content:center;padding:20px;overflow:hidden}.card{width:100%;max-width:560px;position:relative;z-index:2;padding:28px;border-radius:24px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);backdrop-filter:blur(12px);box-shadow:0 20px 60px rgba(0,0,0,.45)}h1{text-align:center;margin:0 0 10px;font-size:2.4rem}p{text-align:center;opacity:.95;margin-bottom:24px;line-height:1.5}form{display:grid;gap:12px}input,button{width:100%;padding:14px 16px;border:none;border-radius:14px;font-size:1rem}input{background:rgba(255,255,255,.96);color:#1b1324}button{cursor:pointer;color:#fff;font-weight:bold;background:linear-gradient(135deg,#ff4fa2,#9c52ff)}.note{font-size:.95rem;text-align:center;margin-top:14px;opacity:.88}.flash{margin-top:14px;padding:10px 12px;background:rgba(255,230,138,.12);border:1px solid rgba(255,230,138,.35);border-radius:12px;color:#ffe68a;text-align:center;font-weight:bold}.confetti{position:fixed;top:-24px;width:10px;height:18px;opacity:.85;animation:fall linear infinite;z-index:1}@keyframes fall{to{transform:translateY(110vh) rotate(740deg)}}
</style></head><body><div id="confetti-box"></div><div class="card"><h1>Feliz Aniversário</h1><p>Qual aniversário deseja participar?</p><form method="post"><input name="birthday_name" placeholder="Digite o nome do aniversariante" required><button type="submit">Entrar</button></form><div class="note">Digite <b>fenrorbot</b> para criar um aniversário.</div>{% with messages = get_flashed_messages() %}{% if messages %}{% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}{% endif %}{% endwith %}</div><script>const colors=["#ff5ea8","#ffd166","#8aff80","#7ed7ff","#d0a2ff","#ffffff"];const box=document.getElementById("confetti-box");for(let i=0;i<110;i++){const piece=document.createElement("div");piece.className="confetti";piece.style.left=(Math.random()*100)+"vw";piece.style.background=colors[Math.floor(Math.random()*colors.length)];piece.style.animationDuration=(4+Math.random()*5)+"s";piece.style.animationDelay=(Math.random()*5)+"s";piece.style.transform="rotate("+(Math.random()*360)+"deg)";box.appendChild(piece);}</script></body></html>'''

CREATE_HTML = r'''<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Criar aniversário</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;color:#fff;background:linear-gradient(155deg,#10081a 0%,#1f1033 55%,#12071d 100%);padding:18px}.wrap{max-width:840px;margin:0 auto;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:24px;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.4)}h1{text-align:center;margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}label{display:block;margin-top:12px;margin-bottom:6px;font-weight:bold}input,textarea,button{width:100%;border:none;border-radius:14px;padding:12px 14px;font-size:1rem}input,textarea{background:rgba(255,255,255,.96);color:#1d1529}textarea{min-height:88px;resize:vertical}.text-block{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:12px;margin-top:12px}.btn{cursor:pointer;font-weight:bold;color:#fff;background:linear-gradient(135deg,#ff4fa2,#8e5bff);margin-top:14px}.btn.secondary{background:linear-gradient(135deg,#6f52ff,#4aa9ff)}.help{margin-top:6px;font-size:.92rem;opacity:.9}.flash{margin-top:12px;padding:10px 12px;background:rgba(255,230,138,.12);border:1px solid rgba(255,230,138,.35);border-radius:12px;color:#ffe68a;font-weight:bold}a{color:#9dd8ff;text-decoration:none}</style></head><body><div class="wrap"><h1>Criar aniversário</h1><form method="post" enctype="multipart/form-data" id="createForm"><div class="grid"><div><label>Nome do aniversariante</label><input type="text" name="birthday_name" required></div><div><label>Data do aniversário</label><input type="date" name="birthday_date" required></div></div><label>Seu nome</label><input type="text" name="creator_name" required><div id="texts-area"><div class="text-block"><label>Texto 1 (opcional)</label><textarea name="text_1" maxlength="80" placeholder="Até 80 caracteres"></textarea><div class="help">Máximo: 80 caracteres.</div></div></div><button type="button" class="btn secondary" id="addTextBtn">+ Adicionar outro texto</button><label>Fotos do aniversariante</label><input type="file" name="photos" id="photos" accept="image/*" multiple required><div class="help">Mínimo 3, máximo 10 fotos.</div><label>Música</label><input type="file" name="music" id="music" accept="audio/*" required><div class="help">Máximo 1 música, com até 3 minutos.</div><button class="btn" type="submit">Criar aniversário</button></form><div class="help" style="margin-top:16px;"><a href="{{ url_for('home') }}">Voltar</a></div>{% with messages = get_flashed_messages() %}{% if messages %}{% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}{% endif %}{% endwith %}</div><script>let textCount=1;const maxTexts=5;document.getElementById("addTextBtn").addEventListener("click",()=>{if(textCount>=maxTexts){alert("O limite é 5 textos.");return;}textCount++;const area=document.getElementById("texts-area");const block=document.createElement("div");block.className="text-block";block.innerHTML=`<label>Texto ${textCount} (opcional)</label><textarea name="text_${textCount}" maxlength="80" placeholder="Até 80 caracteres"></textarea><div class="help">Máximo: 80 caracteres.</div>`;area.appendChild(block);if(textCount>=maxTexts){document.getElementById("addTextBtn").disabled=true;document.getElementById("addTextBtn").style.opacity="0.6";}});document.getElementById("createForm").addEventListener("submit",async(e)=>{const photos=document.getElementById("photos").files;const music=document.getElementById("music").files[0];if(photos.length<3||photos.length>10){e.preventDefault();alert("Envie entre 3 e 10 fotos.");return;}if(!music){e.preventDefault();alert("Envie uma música.");return;}const duration=await new Promise((resolve)=>{const audio=document.createElement("audio");audio.preload="metadata";audio.onloadedmetadata=()=>{window.URL.revokeObjectURL(audio.src);resolve(audio.duration||0)};audio.src=URL.createObjectURL(music);});if(duration>180){e.preventDefault();alert("A música precisa ter no máximo 3 minutos.");}});</script></body></html>'''

JOIN_HTML = r'''<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Entrar no aniversário</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;padding:20px;font-family:Arial,sans-serif;color:#fff;background:linear-gradient(145deg,#0c0613,#1a0f2b,#10081a);display:flex;align-items:center;justify-content:center}.card{width:100%;max-width:560px;padding:28px;border-radius:24px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);backdrop-filter:blur(12px)}h1{text-align:center;margin-top:0}p{text-align:center;line-height:1.5}form{display:grid;gap:12px;margin-top:18px}input,button{width:100%;padding:14px 16px;border-radius:14px;border:none;font-size:1rem}input{background:rgba(255,255,255,.96);color:#1d1529}button{cursor:pointer;color:#fff;font-weight:bold;background:linear-gradient(135deg,#ff4fa2,#8e5bff)}.flash{margin-top:12px;padding:10px 12px;background:rgba(255,230,138,.12);border:1px solid rgba(255,230,138,.35);border-radius:12px;color:#ffe68a;text-align:center;font-weight:bold}a{color:#9dd8ff;text-decoration:none}</style></head><body><div class="card"><h1>Aniversário de {{ event['birthday_name'] }}</h1><p>Escreva seu nome para entrar.</p><form method="post"><input name="person_name" placeholder="Seu nome" required><button type="submit">Entrar no aniversário</button></form><p style="margin-top:18px;">Data do aniversário: <b>{{ event['birthday_date'] }}</b></p><p><a href="{{ url_for('home') }}">Voltar</a></p>{% with messages = get_flashed_messages() %}{% if messages %}{% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}{% endif %}{% endwith %}</div></body></html>'''

ROOM_HTML = r'''<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Aniversário</title><script src="https://download.agora.io/sdk/release/AgoraRTC_N.js"></script><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:Arial,sans-serif;color:#fff;background:radial-gradient(circle at center, rgba(255,255,255,.04) 0%, transparent 30%),linear-gradient(160deg,#09050f,#160b24,#0f0717);overflow-x:hidden}.topbar{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:14px 16px;position:sticky;top:0;background:rgba(8,5,14,.76);backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,.08);z-index:20}.title{font-weight:bold;font-size:1.05rem}.actions{display:flex;gap:8px;flex-wrap:wrap}button{border:none;border-radius:12px;padding:10px 14px;font-size:.95rem;cursor:pointer;color:#fff;font-weight:bold}.cam-btn{background:linear-gradient(135deg,#4aa9ff,#6c5cff)}.start-btn{background:linear-gradient(135deg,#ff4fa2,#8e5bff)}.leave-btn{background:linear-gradient(135deg,#4c4455,#2b2332)}.main{padding:16px;display:grid;gap:16px}.message{text-align:center;font-weight:bold;color:#ffe68a;padding:8px 12px}.tiny-note{text-align:center;opacity:.8;font-size:.88rem}.stage{position:relative;min-height:calc(100vh - 170px);border-radius:22px;background:radial-gradient(circle at center, rgba(255,255,255,.05), rgba(255,255,255,.01));border:1px solid rgba(255,255,255,.08);overflow:hidden}.center-card,.slot{position:absolute;width:150px;height:106px;border-radius:18px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;text-align:center;padding:10px;box-shadow:0 12px 30px rgba(0,0,0,.28);overflow:hidden;transition:transform .6s ease,width .6s ease,height .6s ease,box-shadow .6s ease}.center-card{left:50%;top:50%;transform:translate(-50%,-50%);width:220px;height:160px;z-index:5;background:linear-gradient(145deg, rgba(255,94,168,.18), rgba(142,91,255,.18))}.center-card.grow{width:min(70vw,520px);height:min(55vw,360px);box-shadow:0 0 0 2px rgba(255,255,255,.2),0 30px 80px rgba(255,94,168,.25)}video{width:100%;height:100%;object-fit:cover;border-radius:18px;background:#000}.center-inner,.slot-inner{width:100%;height:100%;position:relative}.overlay-label{position:absolute;left:8px;right:8px;bottom:8px;padding:6px 8px;border-radius:10px;background:rgba(0,0,0,.45);font-size:.9rem;font-weight:bold;z-index:3}.slot.empty{opacity:.35;border-style:dashed}.showcase{display:none;max-width:860px;margin:0 auto;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:24px;padding:16px;text-align:center}.showcase.active{display:block}.showcase img{width:min(100%,720px);max-height:420px;object-fit:contain;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.22)}.showcase-text{margin-top:12px;min-height:52px;font-size:1.15rem;font-weight:bold;color:#fff2b0}.footer-note{text-align:center;opacity:.85;font-size:.95rem;margin-top:6px;padding-bottom:18px}.p1{left:4%;top:6%}.p2{left:28%;top:3%}.p3{left:68%;top:3%}.p4{right:4%;top:6%}.p5{left:2%;top:38%}.p6{right:2%;top:38%}.p7{left:4%;bottom:6%}.p8{left:28%;bottom:3%}.p9{left:68%;bottom:3%}.p10{right:4%;bottom:6%}@media (max-width:860px){.slot,.center-card{width:118px;height:88px;font-size:.9rem}.center-card{width:180px;height:126px}.stage{min-height:720px}}@media (max-width:560px){.stage{min-height:860px}.slot{width:104px;height:84px}.center-card{width:180px;height:130px}.p1{left:3%;top:4%}.p2{left:34%;top:3%}.p3{right:34%;top:3%}.p4{right:3%;top:4%}.p5{left:1.5%;top:30%}.p6{right:1.5%;top:30%}.p7{left:3%;bottom:4%}.p8{left:34%;bottom:3%}.p9{right:34%;bottom:3%}.p10{right:3%;bottom:4%}}</style></head><body><div class="topbar"><div class="title">🎉 Aniversário de {{ event['birthday_name'] }} | Você: {{ current_name }}</div><div class="actions"><button class="cam-btn" id="camBtn">Entrar na chamada</button>{% if current_role == 'creator' %}<button class="start-btn" id="startBtn">Comemorar</button>{% endif %}<button class="leave-btn" onclick="window.location='{{ url_for('home') }}'">Sair</button></div></div><div class="main"><div class="message">{{ welcome_message }}</div><div class="tiny-note">Se AGORA_APP_ID e token estiverem certos, a chamada funciona de verdade.</div><div class="showcase" id="showcase"><img id="showcaseImg" src="" alt="Foto"><div class="showcase-text" id="showcaseText"></div><audio id="partyAudio" src="{{ url_for('uploaded_file', event_id=event_id, filename=event['music']) }}"></audio></div><div class="stage"><div class="center-card" id="centerCard"><div class="center-inner" id="centerInner"><div style="font-weight:bold">🎂 {{ event['birthday_name'] }}</div></div></div>{% for idx in range(1, 11) %}<div class="slot p{{ idx }}" id="slot{{ idx }}"><div class="slot-inner" id="slotInner{{ idx }}"><div>Vazio</div></div></div>{% endfor %}</div><div class="footer-note">Criador e aniversariante precisam entrar na chamada para começar.</div></div><script>const EVENT_ID={{ event_id|tojson }};const CURRENT_NAME={{ current_name|tojson }};const CURRENT_ROLE={{ current_role|tojson }};const BIRTHDAY_NAME={{ event['birthday_name']|tojson }};const PHOTOS={{ photo_urls|tojson }};const TEXTS={{ texts|tojson }};const STARTED={{ event.get('started', False)|tojson }};const AGORA_APP_ID={{ agora_app_id|tojson }};const AGORA_TEMP_TOKEN={{ agora_temp_token|tojson }};const CHANNEL_NAME=("party_"+EVENT_ID).replace(/[^a-zA-Z0-9_]/g, "_");let client=null;let localAudioTrack=null;let localVideoTrack=null;let joinedAgora=false;let cycleStarted=false;const remoteUsers=new Map();const centerCard=document.getElementById("centerCard");const centerInner=document.getElementById("centerInner");const showcase=document.getElementById("showcase");const showcaseImg=document.getElementById("showcaseImg");const showcaseText=document.getElementById("showcaseText");const partyAudio=document.getElementById("partyAudio");const camBtn=document.getElementById("camBtn");const startBtn=document.getElementById("startBtn");function uidForName(name){let hash=0;for(let i=0;i<name.length;i++){hash=((hash<<5)-hash)+name.charCodeAt(i);hash|=0;}return String(Math.abs(hash)).slice(0,9)||String(Math.floor(Math.random()*999999999));}async function fetchState(){const res=await fetch(`/api/event/${EVENT_ID}`);const data=await res.json();renderParticipants(data);if(data.started&&!cycleStarted)startCelebration();}function renderParticipants(data){const participants=data.participants||[];const birthday=participants.find(p=>normalize(p.name)===normalize(BIRTHDAY_NAME));renderCenter(birthday);const around=participants.filter(p=>normalize(p.name)!==normalize(BIRTHDAY_NAME)).slice(0,10);for(let i=1;i<=10;i++){const slot=document.getElementById(`slot${i}`);const inner=document.getElementById(`slotInner${i}`);const p=around[i-1];if(!p){slot.classList.add("empty");inner.innerHTML='<div>Vazio</div>';continue;}slot.classList.remove("empty");const remoteId='remote_'+uidForName(p.name);const isMe=normalize(p.name)===normalize(CURRENT_NAME);if(isMe&&joinedAgora&&localVideoTrack){inner.innerHTML=`<div id="local_slot_video" style="width:100%;height:100%"></div><div class="overlay-label">${escapeHtml(p.name)}</div>`;setTimeout(()=>localVideoTrack.play('local_slot_video'),0);}else if(remoteUsers.has(remoteId)){inner.innerHTML=`<div id="${remoteId}" style="width:100%;height:100%"></div><div class="overlay-label">${escapeHtml(p.name)}</div>`;const info=remoteUsers.get(remoteId);setTimeout(()=>info.videoTrack&&info.videoTrack.play(remoteId),0);}else{inner.innerHTML=`<div style="font-weight:bold;white-space:pre-line">${escapeHtml(p.name)}${p.camera_ready?'\n📷 na chamada':''}</div>`;}}}function renderCenter(birthdayParticipant){const birthdayRemoteId='remote_'+uidForName(BIRTHDAY_NAME);const isBirthdayCurrent=normalize(CURRENT_NAME)===normalize(BIRTHDAY_NAME);if(isBirthdayCurrent&&joinedAgora&&localVideoTrack){centerInner.innerHTML=`<div id="local_center_video" style="width:100%;height:100%"></div><div class="overlay-label">🎂 ${escapeHtml(BIRTHDAY_NAME)}</div>`;setTimeout(()=>localVideoTrack.play('local_center_video'),0);}else if(remoteUsers.has(birthdayRemoteId)){centerInner.innerHTML=`<div id="${birthdayRemoteId}" style="width:100%;height:100%"></div><div class="overlay-label">🎂 ${escapeHtml(BIRTHDAY_NAME)}</div>`;const info=remoteUsers.get(birthdayRemoteId);setTimeout(()=>info.videoTrack&&info.videoTrack.play(birthdayRemoteId),0);}else{centerInner.innerHTML=`<div style="font-weight:bold;white-space:pre-line">🎂 ${escapeHtml(BIRTHDAY_NAME)}${birthdayParticipant&&birthdayParticipant.camera_ready?'\n📷 na chamada':''}</div>`;}}async function resolveParticipantNameByUid(uid){const res=await fetch(`/api/event/${EVENT_ID}`);const data=await res.json();for(const p of (data.participants||[])){if(uidForName(p.name)===uid)return p.name;}return null;}async function joinAgoraCall(){if(!AGORA_APP_ID){alert('Falta configurar AGORA_APP_ID no Render.');return;}if(joinedAgora)return;try{client=AgoraRTC.createClient({mode:'rtc',codec:'vp8'});client.on('user-published',async(user,mediaType)=>{await client.subscribe(user,mediaType);const name=(await resolveParticipantNameByUid(String(user.uid)))||'Participante';remoteUsers.set('remote_'+String(user.uid),{name,videoTrack:user.videoTrack||null});if(mediaType==='audio'&&user.audioTrack)user.audioTrack.play();if(mediaType==='video')await fetchState();});client.on('user-unpublished',async(user,mediaType)=>{if(mediaType==='video'){remoteUsers.delete('remote_'+String(user.uid));await fetchState();}});client.on('user-left',async(user)=>{remoteUsers.delete('remote_'+String(user.uid));await fetchState();});const uid=uidForName(CURRENT_NAME);await client.join(AGORA_APP_ID,CHANNEL_NAME,AGORA_TEMP_TOKEN||null,uid);[localAudioTrack,localVideoTrack]=await AgoraRTC.createMicrophoneAndCameraTracks();await client.publish([localAudioTrack,localVideoTrack]);joinedAgora=true;camBtn.textContent='Na chamada';camBtn.disabled=true;await fetch(`/api/event/${EVENT_ID}/camera`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:CURRENT_NAME,ready:true})});await fetchState();}catch(err){console.error(err);alert('Não consegui entrar na chamada. Confere AGORA_APP_ID e token.');}}if(camBtn)camBtn.addEventListener('click',joinAgoraCall);if(startBtn)startBtn.addEventListener('click',async()=>{const res=await fetch(`/api/event/${EVENT_ID}/start`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:CURRENT_NAME})});const data=await res.json();if(!data.ok){alert(data.message);return;}startCelebration();});function startCelebration(){if(cycleStarted)return;cycleStarted=true;showcase.classList.add('active');partyAudio.currentTime=0;partyAudio.play().catch(()=>{});const items=[];for(let i=0;i<PHOTOS.length;i++){items.push({type:'photo',value:PHOTOS[i]});if(TEXTS[i])items.push({type:'text',value:TEXTS[i]});}for(let i=PHOTOS.length;i<TEXTS.length;i++)items.push({type:'text',value:TEXTS[i]});if(items.length===0){finishCelebration();return;}let index=0;const interval=setInterval(()=>{const item=items[index];if(item.type==='photo'){showcaseImg.style.display='inline-block';showcaseImg.src=item.value;showcaseText.textContent='';}else{showcaseImg.style.display='none';showcaseText.textContent=item.value;}index++;if(index>=items.length){clearInterval(interval);setTimeout(finishCelebration,2200);}},2800);}function finishCelebration(){centerCard.classList.add('grow');showcaseText.textContent=`🎉 Feliz aniversário, ${BIRTHDAY_NAME}!`;if(showcaseImg.src)showcaseImg.style.display='inline-block';}function normalize(text){return (text||'').trim().toLowerCase().replace(/\s+/g,' ')}function escapeHtml(text){return (text||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}fetchState();setInterval(fetchState,2500);if(STARTED)startCelebration();</script></body></html>'''

@app.route('/', methods=['GET','POST'])
def home():
    if request.method == 'POST':
        birthday_name = (request.form.get('birthday_name') or '').strip()
        if not birthday_name:
            flash('Digite um nome.')
            return redirect(url_for('home'))
        if birthday_name == 'fenrorbot':
            return redirect(url_for('create_event'))
        event_id, event = event_by_birthday_name(birthday_name)
        if not event_id:
            flash('Aniversário não encontrado.')
            return redirect(url_for('home'))
        return redirect(url_for('join_page', event_id=event_id))
    return render_template_string(HOME_HTML)

@app.route('/create', methods=['GET','POST'])
def create_event():
    if request.method == 'POST':
        birthday_name = (request.form.get('birthday_name') or '').strip()
        birthday_date = (request.form.get('birthday_date') or '').strip()
        creator_name = (request.form.get('creator_name') or '').strip()
        texts = []
        for i in range(1, 6):
            text = (request.form.get(f'text_{i}') or '').strip()
            if text:
                if len(text) > 80:
                    flash(f'O texto {i} passou de 80 caracteres.')
                    return redirect(url_for('create_event'))
                texts.append(text)
        if not birthday_name or not birthday_date or not creator_name:
            flash('Preencha nome do aniversariante, data e seu nome.')
            return redirect(url_for('create_event'))
        existing_id, _ = event_by_birthday_name(birthday_name)
        if existing_id:
            flash('Já existe um aniversário com esse nome.')
            return redirect(url_for('create_event'))
        photos = [p for p in request.files.getlist('photos') if p and p.filename]
        music = request.files.get('music')
        if len(photos) < 3 or len(photos) > 10:
            flash('Envie entre 3 e 10 fotos.')
            return redirect(url_for('create_event'))
        if not music or not music.filename:
            flash('Envie uma música.')
            return redirect(url_for('create_event'))
        if not all(allowed_image(p.filename) for p in photos):
            flash('Uma ou mais fotos têm formato inválido.')
            return redirect(url_for('create_event'))
        if not allowed_audio(music.filename):
            flash('Formato de música inválido.')
            return redirect(url_for('create_event'))
        event_id = str(uuid.uuid4())[:12]
        event_dir = UPLOADS_DIR / event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        saved_photos = []
        for idx, photo in enumerate(photos, start=1):
            ext = photo.filename.rsplit('.', 1)[-1].lower()
            filename = secure_filename(f'photo_{idx}.{ext}')
            photo.save(event_dir / filename)
            saved_photos.append(filename)
        music_ext = music.filename.rsplit('.', 1)[-1].lower()
        music_name = secure_filename(f'music.{music_ext}')
        music.save(event_dir / music_name)
        event = {'id': event_id, 'birthday_name': birthday_name, 'birthday_date': birthday_date, 'creator_name': creator_name, 'texts': texts, 'photos': saved_photos, 'music': music_name, 'started': False, 'created_at': now_iso(), 'participants': [{'name': creator_name, 'role': 'creator', 'camera_ready': False, 'joined_at': now_iso(), 'last_seen': now_iso()},{'name': birthday_name, 'role': 'birthday', 'camera_ready': False, 'joined_at': now_iso(), 'last_seen': now_iso()}]}
        update_event(event_id, event)
        session['event_id'] = event_id
        session['person_name'] = creator_name
        flash('Aniversário criado com sucesso.')
        return redirect(url_for('room', event_id=event_id))
    return render_template_string(CREATE_HTML)

@app.route('/join/<event_id>', methods=['GET','POST'])
def join_page(event_id):
    event = get_event(event_id)
    if not event:
        flash('Aniversário não encontrado.')
        return redirect(url_for('home'))
    if request.method == 'POST':
        person_name = (request.form.get('person_name') or '').strip()
        if not person_name:
            flash('Digite seu nome.')
            return redirect(url_for('join_page', event_id=event_id))
        today = date.today().isoformat()
        if today < event['birthday_date']:
            flash('o aniversário não começou ainda, aguarde!')
            return redirect(url_for('join_page', event_id=event_id))
        if today > event['birthday_date']:
            flash('chegou na hora em? aniversário já acabou')
            return redirect(url_for('join_page', event_id=event_id))
        if not participant_exists(event, person_name):
            if len(event.get('participants', [])) >= 11:
                flash('Esse aniversário já atingiu o limite de 11 participantes.')
                return redirect(url_for('join_page', event_id=event_id))
            join_event(event_id, person_name)
        else:
            join_event(event_id, person_name)
        session['event_id'] = event_id
        session['person_name'] = person_name
        return redirect(url_for('room', event_id=event_id))
    return render_template_string(JOIN_HTML, event=event)

@app.route('/room/<event_id>')
def room(event_id):
    event = get_event(event_id)
    if not event:
        flash('Aniversário não encontrado.')
        return redirect(url_for('home'))
    current_name = session.get('person_name')
    if not current_name:
        flash('Entre com seu nome primeiro.')
        return redirect(url_for('join_page', event_id=event_id))
    today = date.today().isoformat()
    if today < event['birthday_date']:
        flash('o aniversário não começou ainda, aguarde!')
        return redirect(url_for('join_page', event_id=event_id))
    if today > event['birthday_date']:
        flash('chegou na hora em? aniversário já acabou')
        return redirect(url_for('join_page', event_id=event_id))
    if not participant_exists(event, current_name):
        if len(event.get('participants', [])) >= 11:
            flash('Esse aniversário já atingiu o limite de 11 participantes.')
            return redirect(url_for('join_page', event_id=event_id))
        join_event(event_id, current_name)
    current_role = role_of(event, current_name)
    if current_role == 'creator':
        welcome_message = 'bem vindo, pode começar o aniversário quando quiser!'
    elif current_role == 'birthday':
        welcome_message = f"BEM VINDO, FELIZ ANIVERSÁRIO {event['birthday_name']}!!!"
    else:
        welcome_message = f"seja bem vindo ao aniversário de {event['birthday_name']}! Aguarde o aniversário começar, se prepare!"
    photo_urls = [url_for('uploaded_file', event_id=event_id, filename=f) for f in event.get('photos', [])]
    return render_template_string(ROOM_HTML, event=event, event_id=event_id, current_name=current_name, current_role=current_role, welcome_message=welcome_message, photo_urls=photo_urls, texts=event.get('texts', []), agora_app_id=AGORA_APP_ID, agora_temp_token=AGORA_TEMP_TOKEN)

@app.route('/uploads/<event_id>/<path:filename>')
def uploaded_file(event_id, filename):
    return send_from_directory(UPLOADS_DIR / event_id, filename)

@app.route('/api/event/<event_id>')
def api_event(event_id):
    event = get_event(event_id)
    if not event:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'id': event['id'], 'birthday_name': event['birthday_name'], 'birthday_date': event['birthday_date'], 'creator_name': event['creator_name'], 'started': event.get('started', False), 'participants': event.get('participants', [])})

@app.route('/api/event/<event_id>/camera', methods=['POST'])
def api_camera(event_id):
    event = get_event(event_id)
    if not event:
        return jsonify({'ok': False, 'message': 'Evento não encontrado.'}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    ready = bool(data.get('ready'))
    p = find_participant(event, name)
    if not p:
        return jsonify({'ok': False, 'message': 'Participante não encontrado.'}), 404
    p['camera_ready'] = ready
    p['last_seen'] = now_iso()
    update_event(event_id, event)
    return jsonify({'ok': True})

@app.route('/api/event/<event_id>/start', methods=['POST'])
def api_start(event_id):
    event = get_event(event_id)
    if not event:
        return jsonify({'ok': False, 'message': 'Evento não encontrado.'}), 404
    data = request.get_json(silent=True) or {}
    current_name = (data.get('name') or '').strip()
    if normalize(current_name) != normalize(event['creator_name']):
        return jsonify({'ok': False, 'message': 'Só o criador pode começar.'}), 403
    creator = find_participant(event, event['creator_name'])
    birthday = find_participant(event, event['birthday_name'])
    if not creator or not creator.get('camera_ready'):
        return jsonify({'ok': False, 'message': 'O criador precisa entrar na chamada.'})
    if not birthday or not birthday.get('camera_ready'):
        return jsonify({'ok': False, 'message': 'O aniversariante precisa entrar na chamada.'})
    event['started'] = True
    update_event(event_id, event)
    return jsonify({'ok': True, 'message': 'Aniversário começou!'})

if __name__ == '__main__':
    app.run(debug=True)
