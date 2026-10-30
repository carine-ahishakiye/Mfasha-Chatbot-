(function(){
  'use strict';
  var STORAGE_KEY='mfasha-conversations-v1';var ASR_URL=window.MFASHA_ASR_URL||'';var TTS_URL=window.MFASHA_TTS_URL||'';async function fetchWithFallback(remote,local,opts){if(remote){try{var c=new AbortController();var t=setTimeout(function(){c.abort();},8000);var r=await fetch(remote,Object.assign({signal:c.signal},opts));clearTimeout(t);if(r.ok)return r;}catch(e){}}return fetch(local,opts);}
  var $=function(id){return document.getElementById(id);};
  var app=$('app'),chatForm=$('chat-form'),questionBox=$('question'),sendButton=$('send-button'),microphoneButton=$('microphone'),micIcon=$('mic-icon'),micLabel=$('mic-label'),statusLine=$('status-line'),thread=$('thread'),emptyState=$('empty-state'),historyList=$('history-list'),chatScroll=$('chat-scroll');
  var conversations=[],activeConversationId=null,isBusy=false,recorder=null,micStream=null,recordTimer=null,audioPlayer=null,audioUrl=null,activeSpeakButton=null,speechRequestId=0;

  function setStatus(text){statusLine.textContent=text||'';}
  function saveConversations(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(conversations));}catch(e){setStatus('Ntabwo amateka yabitswe kuri iki gikoresho.');}}
  function loadConversations(){try{var saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]');if(Array.isArray(saved))conversations=saved;}catch(e){conversations=[];}conversations=conversations.filter(function(c){return c&&c.id&&Array.isArray(c.items);});renderHistory();}
  function getActiveConversation(){return conversations.find(function(c){return c.id===activeConversationId;})||null;}

  function renderHistory(){
    historyList.replaceChildren();
    if(!conversations.length){var empty=document.createElement('p');empty.className='no-history';empty.textContent='Nta kiganiro kiraboneka.';historyList.appendChild(empty);return;}
    conversations.slice().sort(function(a,b){return(b.updated||b.created||0)-(a.updated||a.created||0);}).forEach(function(c){
      var row=document.createElement('div');row.className='history-row';var button=document.createElement('button');button.type='button';button.className='history-item'+(c.id===activeConversationId?' active':'');button.textContent=c.title||'Ikiganiro gishya';button.title=button.textContent;button.addEventListener('click',function(){openConversation(c.id);});var del=document.createElement('button');del.type='button';del.className='history-del';del.setAttribute('aria-label','Siba iki kiganiro');del.title='Siba iki kiganiro';del.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>';del.addEventListener('click',function(ev){ev.stopPropagation();deleteConversation(c.id);});row.appendChild(button);row.appendChild(del);historyList.appendChild(row);
    });
  }

  function deleteConversation(id){if(!window.confirm('Urashaka gusiba iki kiganiro?'))return;conversations=conversations.filter(function(c){return c.id!==id;});saveConversations();if(id===activeConversationId)beginNewChat();else renderHistory();}
  function showEmpty(show){emptyState.hidden=!show;}
  function beginNewChat(){stopSpeech();activeConversationId=null;thread.replaceChildren();showEmpty(true);renderHistory();chatScroll.scrollTop=0;app.classList.remove('open');questionBox.focus();}
  function openConversation(id){
    var c=conversations.find(function(item){return item.id===id;});if(!c)return;stopSpeech();activeConversationId=id;thread.replaceChildren();showEmpty(false);
    c.items.forEach(function(item){var turn=createTurn(item.question);if(item.answer)renderAnswer(turn,item.answer,item,true);else showAnswerError(turn,'Iki gisubizo nticyabitswe.');});
    renderHistory();chatScroll.scrollTop=chatScroll.scrollHeight;app.classList.remove('open');
  }

  function createTurn(question){
    var article=document.createElement('article');article.className='turn';var row=document.createElement('div');row.className='question';var bubble=document.createElement('div');bubble.textContent=question;row.appendChild(bubble);article.appendChild(row);
    var card=document.createElement('section');card.className='answer';var body=document.createElement('div');card.appendChild(body);article.appendChild(card);thread.appendChild(article);return{article:article,card:card,body:body};
  }
  function showThinking(turn){var p=document.createElement('p');p.className='thinking';p.textContent='Ndimo gushaka igisubizo…';turn.body.appendChild(p);chatScroll.scrollTop=chatScroll.scrollHeight;}
  function makeButton(text){var b=document.createElement('button');b.type='button';b.className='tool';b.textContent=text;return b;}
  async function feedback(item,passageId,vote,button){if(item.vote||item.feedbackPending)return;item.feedbackPending=true;button.disabled=true;try{var response=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:item.question,passage_id:passageId||null,vote:vote})});if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');}item.vote=vote;button.classList.add('selected');saveConversations();}catch(error){setStatus(error.message||'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');}finally{item.feedbackPending=false;button.disabled=!!item.vote;}}

  function renderAnswer(turn,answer,item,quiet){
    turn.body.replaceChildren();turn.card.classList.toggle('refused',!!answer.refused);
    if(!answer.refused&&answer.tier){
      var badge=document.createElement('span');badge.className='badge '+answer.tier;badge.textContent='Icyizere: '+({high:'kinshi',medium:'giciriritse',low:'gike'}[answer.tier]||'ntikizwi');turn.body.appendChild(badge);
      if(answer.tier==='medium'||answer.tier==='low'){var note=document.createElement('p');note.className='note';note.textContent=answer.tier==='low'?'Iki gisubizo nticyizewe bihagije. Genzura n’andi makuru.':'Genzura n’andi makuru kugira ngo wemeze iki gisubizo.';turn.body.appendChild(note);}}
    var text=document.createElement('p');text.className='answer-text';text.textContent=answer.answer||'Nta gisubizo cyagarutse.';turn.body.appendChild(text);
    if(!answer.refused&&answer.alternatives&&answer.alternatives.length){var details=document.createElement('details');details.className='alternatives';var summary=document.createElement('summary');summary.textContent='Ibindi bisubizo bishoboka ('+answer.alternatives.length+')';details.appendChild(summary);answer.alternatives.forEach(function(value){var p=document.createElement('p');p.className='alternative';p.textContent=value;details.appendChild(p);});turn.body.appendChild(details);}
    var tools=document.createElement('div');tools.className='tools';var speaker=makeButton('Soma igisubizo');speaker.addEventListener('click',function(){speakAnswer(answer.answer||'',speaker);});tools.appendChild(speaker);
    if(!answer.refused){
      var yes=makeButton(item.vote==='helpful'?'Byamfashije ✓':'Byamfashije');yes.disabled=!!item.vote;yes.addEventListener('click',function(){feedback(item,answer.passage_id,'helpful',yes);});
      var no=makeButton(item.vote==='not_helpful'?'Ntibyamfashije ✓':'Ntibyamfashije');no.disabled=!!item.vote;no.addEventListener('click',function(){feedback(item,answer.passage_id,'not_helpful',no);});
      var copy=makeButton('Koporora');copy.addEventListener('click',function(){if(!navigator.clipboard){setStatus('Iyi mushakisha ntishobora gukoporora.');return;}navigator.clipboard.writeText(answer.answer||'').then(function(){setStatus('Igisubizo cyakoporowe.');setTimeout(function(){setStatus('');},1600);}).catch(function(){setStatus('Ntabwo igisubizo cyakoporowe.');});});
      tools.appendChild(yes);tools.appendChild(no);tools.appendChild(copy);}
    turn.body.appendChild(tools);if(!quiet)turn.article.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function showAnswerError(turn,message){turn.body.replaceChildren();var p=document.createElement('p');p.className='error';p.textContent=message;turn.body.appendChild(p);}

  function resetSpeakButton(){if(activeSpeakButton){activeSpeakButton.classList.remove('selected');activeSpeakButton.textContent='Soma igisubizo';activeSpeakButton=null;}}
  function stopSpeech(){speechRequestId++;if(audioPlayer){audioPlayer.onended=null;audioPlayer.onerror=null;audioPlayer.pause();audioPlayer=null;}if(audioUrl){URL.revokeObjectURL(audioUrl);audioUrl=null;}resetSpeakButton();}
  function speechNote(header){var h=(header||'').toLowerCase();if(h.indexOf('number')>-1)return 'Interuro zirimo imibare ntizasomwe. Zisome mu nyandiko.';if(h.indexOf('first')>-1)return 'Hasomwe igice cya mbere gusa.';return '';}
  async function speakAnswer(text,button){
    if(button&&activeSpeakButton===button){stopSpeech();setStatus('');return;}
    stopSpeech();var requestId=speechRequestId;activeSpeakButton=button||null;if(button){button.classList.add('selected');button.textContent='Hagarika gusoma';}setStatus('Ndimo gutegura amajwi…');
    try{
      var response=await fetchWithFallback(TTS_URL,'/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:(text||'').slice(0,5000)})});
      if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ijwi ntiryakunze.');}
      var note=speechNote(response.headers.get('X-Notes'));var blob=await response.blob();if(requestId!==speechRequestId)return;
      audioUrl=URL.createObjectURL(blob);audioPlayer=new Audio(audioUrl);setStatus(note?'Ndimo gusoma. '+note:'Ndimo gusoma igisubizo…');
      audioPlayer.onended=function(){if(requestId!==speechRequestId)return;stopSpeech();setStatus(note);};
      audioPlayer.onerror=function(){if(requestId!==speechRequestId)return;stopSpeech();setStatus('Ntabwo ijwi ryakinnye. Ongera ukande “Soma igisubizo”.');};
      await audioPlayer.play();
    }catch(error){if(requestId!==speechRequestId)return;stopSpeech();setStatus(error.message||'Ijwi ntiryakunze.');}
  }

  function resizeQuestion(){questionBox.style.height='auto';questionBox.style.height=Math.min(questionBox.scrollHeight,140)+'px';}
  function setMicIcon(recording){microphoneButton.classList.toggle('recording',recording);microphoneButton.setAttribute('aria-label',recording?'Hagarika gufata amajwi':'Tangira gufata amajwi');micLabel.textContent=recording?'Rangiza':'Vuga';micIcon.innerHTML=recording?'<rect x="6" y="6" width="12" height="12" rx="2"/>':'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/>';}
  function stopMicStream(){if(recordTimer){clearTimeout(recordTimer);recordTimer=null;}if(micStream){micStream.getTracks().forEach(function(track){track.stop();});micStream=null;}}
  function stopRecording(){if(!recorder||recorder.state!=='recording')return;microphoneButton.disabled=true;setStatus('Ndimo gutegura amajwi yawe…');try{recorder.stop();}catch(error){recorder=null;stopMicStream();setMicIcon(false);microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Ntabwo amajwi yafashwe. Ongera ugerageze.');}}

  async function startRecording(){
    if(isBusy||recorder)return;
    if(window.isSecureContext===false&&location.hostname!=='localhost'&&location.hostname!=='127.0.0.1'){setStatus('Koresha uru rubuga kuri HTTPS cyangwa localhost kugira ngo ufungure mikoro.');return;}
    if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia||!window.MediaRecorder){setStatus('Iyi mushakisha ntishobora gufata amajwi.');return;}
    setStatus('Emera gukoresha mikoro nibigusabwa.');
    try{
      micStream=await navigator.mediaDevices.getUserMedia({audio:true});
      var supported=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'];
      var mimeType=MediaRecorder.isTypeSupported?(supported.find(function(type){return MediaRecorder.isTypeSupported(type);})||''):'';
      recorder=new MediaRecorder(micStream,mimeType?{mimeType:mimeType}:undefined);
      var activeRecorder=recorder,chunks=[],failed=false;
      activeRecorder.ondataavailable=function(event){if(event.data&&event.data.size)chunks.push(event.data);};
      activeRecorder.onerror=function(){failed=true;recorder=null;stopMicStream();setMicIcon(false);microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Ntabwo amajwi yafashwe. Reba uruhushya rwa mikoro.');};
      activeRecorder.onstop=async function(){
        var contentType=activeRecorder.mimeType||mimeType||'audio/webm';recorder=null;stopMicStream();setMicIcon(false);if(failed)return;
        var blob=new Blob(chunks,{type:contentType});
        if(!blob.size){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Nta majwi yafashwe. Ongera ugerageze.');return;}
        if(blob.size>20*1024*1024){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Amajwi ni manini cyane. Vuga igihe gito.');return;}
        setStatus('Ndimo kumva ibyo wavuze…');
        try{
          var response=await fetchWithFallback(ASR_URL,'/api/transcribe',{method:'POST',headers:{'Content-Type':contentType},body:blob});
          if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ntabwo amajwi yahinduwe inyandiko.');}
          var data=await response.json();var transcript=(data.text||'').trim();
          if(!transcript){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Nta magambo numvise. Ongera ugerageze.');return;}
          questionBox.value=transcript;resizeQuestion();setStatus('');askQuestion(transcript,false);
        }catch(error){microphoneButton.disabled=false;sendButton.disabled=false;setStatus(error.message||'Ntabwo amajwi yahinduwe inyandiko.');}
      };
      recorder.start();sendButton.disabled=true;setMicIcon(true);setStatus('Ndakumva. Kanda “Rangiza” nurangiza kuvuga.');
      recordTimer=setTimeout(function(){if(recorder&&recorder.state==='recording')stopRecording();},30000);
    }catch(error){stopMicStream();recorder=null;setMicIcon(false);microphoneButton.disabled=false;setStatus('Ntabwo nashoboye gukoresha mikoro. Reba uruhushya rwa mushakisha.');}
  }

  async function askQuestion(question,voiceReply){
    question=(question||'').trim();
    if(question.length>500){setStatus('Ikibazo kirenze inyuguti 500. Gabanya inyandiko mbere yo kohereza.');return;}
    if(!question||isBusy)return;
    stopSpeech();setStatus('');isBusy=true;sendButton.disabled=true;microphoneButton.disabled=true;emptyState.hidden=true;questionBox.value='';resizeQuestion();
    var conversation=getActiveConversation();
    if(!conversation){conversation={id:'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,7),title:question.slice(0,70),created:Date.now(),updated:Date.now(),items:[]};conversations.unshift(conversation);activeConversationId=conversation.id;}
    var item={question:question,answer:null,vote:null};conversation.items.push(item);
    var turn=createTurn(question);showThinking(turn);saveConversations();renderHistory();
    try{
      var response=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:question})});
      if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Habaye ikibazo mu gushaka igisubizo.');}
      var answer=await response.json();item.answer=answer;conversation.updated=Date.now();saveConversations();renderHistory();renderAnswer(turn,answer,item,false);
      if(voiceReply){var speaker=turn.body.querySelector('.tool');if(speaker)speakAnswer(answer.answer||'',speaker);}
    }catch(error){showAnswerError(turn,error.message||'Habaye ikibazo. Ongera ugerageze.');}
    finally{isBusy=false;sendButton.disabled=false;microphoneButton.disabled=false;questionBox.focus();}
  }

  document.querySelectorAll('[data-question]').forEach(function(button){button.addEventListener('click',function(){askQuestion(button.getAttribute('data-question')||'',false);});});
  chatForm.addEventListener('submit',function(event){event.preventDefault();askQuestion(questionBox.value,false);});
  questionBox.addEventListener('input',resizeQuestion);
  questionBox.addEventListener('keydown',function(event){if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();askQuestion(questionBox.value,false);}});
  microphoneButton.addEventListener('click',function(){if(recorder&&recorder.state==='recording')stopRecording();else if(!recorder&&!microphoneButton.disabled)startRecording();});
  $('new-chat').addEventListener('click',beginNewChat);
  var menuButtons=[$('toggle-history'),$('collapse-sidebar')],desktopQuery=window.matchMedia('(min-width:821px)');
  function syncMenu(){var expanded=desktopQuery.matches?!app.classList.contains('collapsed'):app.classList.contains('open');var label=expanded?'Funga ibiganiro byashize':'Fungura ibiganiro byashize';menuButtons.forEach(function(b){b.setAttribute('aria-expanded',expanded?'true':'false');b.setAttribute('aria-label',label);b.title=label;});}
  function toggleMenu(){if(desktopQuery.matches){app.classList.toggle('collapsed');try{localStorage.setItem('mfasha-sidebar',app.classList.contains('collapsed')?'closed':'open');}catch(e){}}else{app.classList.toggle('open');}}
  try{if(localStorage.getItem('mfasha-sidebar')==='closed')app.classList.add('collapsed');}catch(e){}
  menuButtons.forEach(function(b){b.addEventListener('click',toggleMenu);});
  new MutationObserver(syncMenu).observe(app,{attributes:true,attributeFilter:['class']});
  if(desktopQuery.addEventListener)desktopQuery.addEventListener('change',syncMenu);
  syncMenu();
  $('scrim').addEventListener('click',function(){app.classList.remove('open');});
  $('clear-history').addEventListener('click',function(){if(!conversations.length){setStatus('Nta biganiro bihari byo gusiba.');return;}if(!window.confirm('Urashaka gusiba ibiganiro byose?'))return;conversations=[];activeConversationId=null;saveConversations();beginNewChat();renderHistory();});
  document.querySelectorAll('[data-close]').forEach(function(b){b.addEventListener('click',function(){app.classList.remove('open');$('toggle-history').focus();});});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&app.classList.contains('open')){app.classList.remove('open');$('toggle-history').focus();}});
  var brandLink=document.querySelector('.brand');if(brandLink)brandLink.addEventListener('click',function(){location.href='/';});
  loadConversations();
}());
