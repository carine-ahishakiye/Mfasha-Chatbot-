
function mfashaI18nBoot() {
  'use strict';
  var KEY = 'mfasha-lang', lang = 'rw', rwTitle = document.title;
  try { lang = localStorage.getItem(KEY) === 'en' ? 'en' : 'rw'; } catch (e) {}

  var PAIRS = [
    // officer: login
    ["Mfasha ikenera JavaScript kugira ngo ikore. Nyabuneka uyifungure muri porogaramu yawe ushakiramo (browser).", "Mfasha needs JavaScript to work. Please enable it in your browser."],
    ["Mfasha ikenera JavaScript kugira ngo ikore. Nyamuneka uyifungure muri murandasi yawe.", "Mfasha needs JavaScript to work. Please enable it in your browser."],
    ["Simbukira ku bikubiyemo", "Skip to content"],
    ["Subira inyuma", "Back"],
    ["Injira", "Sign in"],
    ["Ahagenewe abakozi b’ubuhinzi bagenzura ibisubizo Mfasha iha abahinzi.", "For agricultural officers who check the answers Mfasha gives to farmers."],
    ["Injira cyangwa ufungure konti", "Sign in or create an account"],
    ["Mfite konti", "I have an account"],
    ["Nshaka konti nshya", "Create a new account"],
    ["Nimero ya telefone", "Phone number"],
    ["Urugero: 0788 123 456", "Example: 0788 123 456"],
    ["PIN yawe", "Your PIN"],
    ["Imibare 4 kugeza kuri 6", "4 to 6 digits"],
    ["Wibagiwe PIN? Baza umuyobozi wawe.", "Forgot your PIN? Ask your supervisor."],
    ["Erekana PIN", "Show PIN"],
    ["Hisha PIN", "Hide PIN"],
    ["Uzakenera kode uhabwa n’umuyobozi wawe. Nta kode, ntushobora gufungura konti.", "You need a code from your supervisor. Without it you cannot create an account."],
    ["Amazina yawe yose", "Your full name"],
    ["Izina ry’idini n’irya se", "First and last name"],
    ["Hitamo PIN", "Choose a PIN"],
    ["Imibare 4–6", "4–6 digits"],
    ["Ongera wandike PIN", "Repeat the PIN"],
    ["Nk’iyo haruguru", "Same as above"],
    ["Ibuka PIN yawe kandi ntuyiheho undi muntu.", "Remember your PIN and do not share it."],
    ["Kode yo gufungura konti", "Account code"],
    ["Ni iyo umuyobozi wawe yaguhaye.", "The one your supervisor gave you."],
    ["Ufunguye konti, wemeye uko dukusanya, tubika kandi dukoresha amakuru yawe.", "By creating an account, you accept how we collect, store and use your information."],
    ["Fungura konti", "Create account"],
    ["Politiki y’ibanga", "Privacy policy"],
    ["Amabwiriza yo gukoresha", "Terms of use"],
    ["Funga", "Close"],
    // officer: dashboard
    ["Abakozi b’ubuhinzi", "Agricultural officers"],
    ["Ibice by’urubuga", "Site sections"],
    ["Suzuma ibisubizo", "Review answers"],
    ["Imibare ya Mfasha", "Mfasha statistics"],
    ["Winjiye nka", "Signed in as"],
    ["Sohoka", "Sign out"],
    ["Muraho", "Hello"],
    ["Hano ubona uko Mfasha ikora: ibibazo bimaze kubazwa, ibimaze gusuzumwa n’ibyafashije abahinzi.", "See how Mfasha is doing: questions asked, answers reviewed and how many helped farmers."],
    ["Imikorere ya Mfasha", "How Mfasha is performing"],
    ["Vugurura", "Refresh"],
    ["Vugurura imibare", "Refresh statistics"],
    ["Vugurura urutonde", "Refresh list"],
    ["Mfasha yasubije abahinzi. Soma buri gisubizo urebe niba ari ukuri kandi gifite umutekano.", "Mfasha has answered farmers. Read each answer and check that it is correct and safe."],
    ["Intambwe eshatu", "Three steps"],
    ["Hitamo igisubizo ku rutonde", "Pick an answer from the list"],
    ["Gisome neza", "Read it carefully"],
    ["Hitamo icyemezo, maze wohereze", "Choose a verdict and send it"],
    ["Ibisubizo", "Answers"],
    ["Ibyo kwerekana", "Show"],
    ["Bitegereje", "Waiting"],
    ["Byose", "All"],
    ["Erekana ibindi", "Show more"],
    ["Ufite nimero y’igisubizo? Yandike hano", "Have an answer number? Type it here"],
    ["Urugero: 125", "Example: 125"],
    ["Shaka", "Find"],
    ["Nta gisubizo uratoranya. Hitamo igisubizo ku rutonde rw’ibumoso (cyangwa wandike nimero yacyo) kugira ngo utangire kugisuzuma.", "No answer selected. Choose an answer from the list on the left (or type its number) to start reviewing."],
    ["Ikibazo cy’umuhinzi", "Farmer’s question"],
    ["Igisubizo cya Mfasha", "Mfasha’s answer"],
    ["Icyemezo cyawe (ni ngombwa)", "Your verdict (required)"],
    ["Ni ukuri", "Correct"],
    ["Igisubizo cyose ni cyo.", "The whole answer is right."],
    ["Ni ukuri igice", "Partly correct"],
    ["Hari ibyo kinyuranyijeho cyangwa kibura.", "Some parts are wrong or missing."],
    ["Si ukuri", "Incorrect"],
    ["Cyakosha cyangwa cyateza ikibazo.", "It is wrong or could cause harm."],
    ["Ibindi usuzuma (tiki ibyo wemeza)", "Other checks (tick what you confirm)"],
    ["Gifitanye isano n’ikibazo", "Relevant to the question"],
    ["Gisubiza ibyo umuhinzi yabajije.", "It answers what the farmer asked."],
    ["Gisobanutse", "Clear"],
    ["Umuhinzi yagisobanukirwa byoroshye.", "A farmer can easily understand it."],
    ["Nta kibazo cy’umutekano kirimo", "No safety concern"],
    ["Nta cyahungabanya ubuzima, amatungo, ibihingwa cyangwa ibidukikije.", "Nothing that could harm health, animals, crops or the environment."],
    ["Icyo wongeraho (si ngombwa)", "Anything to add (optional)"],
    ["Urugero: igisubizo cyari gikwiye kuvuga igipimo cy’ifumbire.", "Example: the answer should have given the fertiliser amount."],
    ["Ohereza isuzuma", "Send review"],
    ["Isuzuma ryawe ribikwa kuri seriveri ya Mfasha, rigakoreshwa mu kunoza ibisubizo. Rimaze koherezwa, ukomeza ku gisubizo gikurikira.", "Your review is stored on the Mfasha server and used to improve answers. Once sent, you move on to the next answer."],
    ["Ibibazo byose", "All questions"],
    ["Byoherejwe ku mukozi", "Referred to an officer"],
    ["Ibisubizo byasuzumwe", "Answers reviewed"],
    ["Byasubijwe", "Answered"],
    ["Igipimo cyo kohereza ku mukozi", "Referral rate"],
    ["Igihe gisanzwe cyo gusubiza", "Average response time"],
    ["Ibitekerezo by’abahinzi", "Farmer feedback"],
    ["Byafashije abahinzi", "Helped farmers"],
    ["Cyoherejwe ku mukozi", "Referred to an officer"],
    ["Ndimo kuvugurura…", "Refreshing…"],
    ["Ntibyavuguruwe. Ongera ugerageze.", "Could not refresh. Try again."],
    ["Ntabwo bishoboka kugera kuri seriveri. Reba murandasi (internet) yawe, maze wongere ugerageze.", "Cannot reach the server. Check your internet connection and try again."],
    ["Igihe cyo kwinjira cyarangiye. Ongera winjire.", "Your session has expired. Please sign in again."],
    ["Iki gisubizo ntikibonetse. Reba nimero maze wongere ugerageze.", "Answer not found. Check the number and try again."],
    ["Hari ibyo wanditse bidahuye. Ubisuzume maze wongere ugerageze.", "Some of what you entered does not match. Please check and try again."],
    ["Wagerageje kenshi PIN itari yo. Ongera ugerageze nyuma y’iminota 5.", "Too many wrong PIN attempts. Try again in 5 minutes."],
    ["Igice cy’abakozi ntikirafungurwa kuri seriveri.", "The officer section is not yet enabled on the server."],
    ["Seriveri ifite ikibazo. Ongera ugerageze mu kanya gato.", "The server has a problem. Try again shortly."],
    ["Habaye ikibazo. Ongera ugerageze.", "Something went wrong. Please try again."],
    ["PIN igomba kuba imibare 4 kugeza kuri 6.", "PIN must be 4 to 6 digits."],
    ["PIN zombi ntizihuye. Ongera ubyandike.", "The two PINs do not match. Please retype them."],
    ["Kode wanditse si yo. Baza umuyobozi wawe kode nyayo.", "That code is wrong. Ask your supervisor for the correct code."],
    ["Iyi nimero ya telefone isanzwe ifite konti. Hitamo “Mfite konti” maze winjire.", "This phone number already has an account. Choose “I have an account” and sign in."],
    ["Gufungura konti ntibirafungurwa kuri seriveri. Baza umuyobozi wawe.", "Account creation is not yet enabled on the server. Ask your supervisor."],
    ["Wagerageje kode itari yo kenshi. Ongera ugerageze nyuma y’iminota 5.", "Too many wrong code attempts. Try again in 5 minutes."],
    ["Reba amazina, nimero ya telefone na PIN maze wongere ugerageze.", "Check your name, phone number and PIN, then try again."],
    ["Nimero ya telefone cyangwa PIN si byo. Ongera urebe maze ugerageze.", "Wrong phone number or PIN. Check and try again."],
    ["Nta bisubizo bitegereje gusuzumwa. Hitamo “Byose” kugira ngo urebe ibisubizo byose.", "No answers waiting for review. Choose “All” to see every answer."],
    ["Nta bisubizo biraboneka. Abahinzi nibabaza ibibazo, bizagaragara hano.", "No answers yet. When farmers ask questions, they will appear here."],
    ["(nta kibazo)", "(no question)"],
    ["Urutonde rw’ibitegereje ntiruraboneka kuri seriveri. Andika nimero y’igisubizo hasi.", "The waiting list is not available on the server. Type an answer number below."],
    ["Andika nimero y’igisubizo (imibare gusa).", "Type the answer number (digits only)."],
    ["Igisubizo ntikigaragara.", "Answer not available."],
    ["Hitamo icyemezo cyawe: “Ni ukuri”, “Ni ukuri igice” cyangwa “Si ukuri”.", "Choose your verdict: “Correct”, “Partly correct” or “Incorrect”."],
    ["Dore igisubizo gikurikira.", "Here is the next answer."],
    ["Hitamo ikindi gisubizo ku rutonde.", "Choose another answer from the list."],
    ["Nta bindi bisubizo bitegereje. Murakoze cyane!", "No more answers are waiting. Thank you very much!"],
    // home
    ["Ibyo ifasha", "What it helps with"],
    ["Uko ikora", "How it works"],
    ["Abakozi", "Officers"],
    ["Tangira", "Start"],
    ["UBUHINZI N'UBWOROZI • MU KINYARWANDA", "FARMING AND LIVESTOCK • IN KINYARWANDA"],
    ["Ubufasha ku buhinzi n'ubworozi, mu", "Help with farming and livestock, in"],
    ["Baza ikibazo cyawe wanditse cyangwa ukoreshe ijwi. Mfasha igushakira igisubizo mu makuru y'ubuhinzi yasuzumwe.", "Ask your question by typing or by voice. Mfasha finds an answer for you in reviewed farming information."],
    ["Baza Mfasha →", "Ask Mfasha →"],
    ["Baza Mfasha ↗", "Ask Mfasha ↗"],
    ["Ndi umukozi w'ubuhinzi", "I am an agricultural officer"],
    ["MFASHA • UBUFASHA MU BUHINZI", "MFASHA • FARMING HELP"],
    ["Ibibazo ushobora kubaza", "Questions you can ask"],
    ["Reba ingero z'ibibazo ushobora kubaza:", "See examples of questions you can ask (the examples are in Kinyarwanda):"],
    ["Andika cyangwa uvuge ikibazo cyawe", "Type or speak your question"],
    ["MFASHA IGUFASHA KURI:", "MFASHA HELPS YOU WITH:"],
    ["Ibihingwa", "Crops"], ["Amatungo", "Livestock"], ["Indwara", "Diseases"], ["Ifumbire", "Fertiliser"], ["Ubutaka", "Soil"], ["Imbuto", "Seeds"],
    ["BYOROSHYE GUKORESHA", "EASY TO USE"],
    ["Uko Mfasha ikora", "How Mfasha works"],
    ["Baza ikibazo", "Ask a question"],
    ["Andika ikibazo cyawe cyangwa ugikoreshe ijwi mu Kinyarwanda.", "Type your question or say it out loud, in Kinyarwanda."],
    ["Shaka igisubizo", "Get an answer"],
    ["Mfasha ishakisha amakuru ajyanye n'ikibazo cyawe mu bubiko bw'amakuru.", "Mfasha looks for information related to your question in its information store."],
    ["Kurikiza inama", "Follow the advice"],
    ["Reba igisubizo cyabonetse. Iyo amakuru adahagije, saba ubufasha bw'umukozi w'ubuhinzi.", "Look at the answer found. If the information is not enough, ask an agricultural officer for help."],
    ["Umufasha mu buhinzi n'ubworozi.", "Your assistant in farming and livestock."],
    ["Umuhinzi", "Farmer"],
    ["Umukozi w'ubuhinzi", "Agricultural officer"],
    ["Mfasha | Umufasha mu buhinzi n'ubworozi", "Mfasha | Your farming and livestock assistant"],
    ["Mfasha – Abakozi b’ubuhinzi", "Mfasha – Agricultural officers"],
    ["Mfasha – Umufasha wawe mu buhinzi n’ubworozi", "Mfasha – Your farming and livestock assistant"],
    ["Baza Mfasha – Umufasha wawe mu buhinzi n’ubworozi", "Ask Mfasha – Your farming and livestock assistant"],
    // chat
    ["Ibiganiro", "Conversations"],
    ["Mfasha, subira ku rupapuro rwa mbere", "Mfasha, back to the first page"],
    ["Funga ibiganiro byashize", "Close past conversations"],
    ["Fungura ibiganiro byashize", "Open past conversations"],
    ["Shakisha mu biganiro", "Search conversations"],
    ["Ikiganiro gishya", "New chat"],
    ["Ibiganiro byashize", "Past conversations"],
    ["Subira ahabanza", "Back to start"],
    ["Siba ibiganiro byose", "Delete all conversations"],
    ["Murakaza neza", "Welcome"],
    ["Nagufasha iki uyu munsi?", "How can I help you today?"],
    ["Mbaza ibibazo ku bihingwa, amatungo, ifumbire n’ubutaka, wandike cyangwa uvuge.", "Ask me about crops, livestock, fertiliser and soil. Type or speak. Please ask in Kinyarwanda."],
    ["Ibibazo byawe n’ibisubizo bibikwa kuri seriveri kugira ngo abakozi b’ubuhinzi babisuzume. Irinde kwandika amazina yawe cyangwa nimero ya telefone.", "Your questions and the answers are stored on the server so agricultural officers can review them. Do not write your name or phone number."],
    ["Ikibazo cyihutirwa? Baza umukozi w’ubuhinzi cyangwa veterineri. Ku miti, imiti y’amatungo n’indwara, ntukishingikirize kuri Mfasha yonyine.", "Urgent problem? Ask an agricultural officer or a veterinarian. For medicines, animal medicines and diseases, do not rely on Mfasha alone."],
    ["Ikiganiro", "Conversation"],
    ["Ikibazo cyawe", "Your question"],
    ["Andika ikibazo cyawe hano", "Type your question here (in Kinyarwanda)"],
    ["Tangira gufata amajwi", "Start recording"],
    ["Hagarika gufata amajwi", "Stop recording"],
    ["Vuga", "Speak"], ["Rangiza", "Finish"], ["Ohereza", "Send"],
    ["Ibibazo byo gutangirira", "Example questions"],
    ["Ubutaka bw’ibirayi", "Potato soil"],
    ["Intama zororoka", "Sheep breeding"],
    ["Aho soya ihunikwa", "Where soya is stored"],
    ["Icyo tubika", "What we store"],
    ["Iyo ubajije, tubika ikibazo cyawe, igisubizo wahawe n’igihe wabajijeho. Ku jwi, tubika inyandiko y’ibyo wavuze. Ntabwo tugusaba amazina, nimero ya telefone cyangwa konti.", "When you ask a question, we store your question, the answer you received and the time you asked. For voice, we store a text transcript of what you said. We do not ask for your name, phone number or an account."],
    ["Ibibazo bishobora kuba birimo amakuru bwite wanditse ubwawe. Irinde kuyandika.", "Questions may contain personal information that you typed yourself. Avoid writing it."],
    ["Icyo tubikira", "Why we store it"],
    ["Abakozi b’ubuhinzi basuzuma ibisubizo kugira ngo bibe byiza kandi bitagira ingaruka mbi. Ntabwo tugurisha amakuru yawe.", "Agricultural officers review answers so they are good and do not cause harm. We do not sell your information."],
    ["Ibiganiro biri kuri telefone yawe", "Conversations on your phone"],
    ["Ibiganiro ubona ku ruhande rw’ibumoso bibikwa kuri telefone yawe. “Siba ibiganiro byose” isiba gusa kopi iri kuri telefone yawe. Kopi iri kuri seriveri ya Mfasha ntisibwa kuri iyo buto.", "The conversations you see on the left are stored on your phone. “Delete all conversations” only deletes the copy on your phone. The copy on the Mfasha server is not deleted by that button."],
    ["Nta konti, nta bumenyi bukwerekeyeho", "No account, no knowledge about you"],
    ["Ntukeneye konti, bityo ntituzi uwo uri we. Ibibazo byawe ntibihuzwa n’izina ryawe cyangwa nimero ya telefone. Ku mpamvu imwe, ntidushobora kubona ibibazo byawe byihariye mu bindi byose.", "You do not need an account, so we do not know who you are. Your questions are not linked to your name or phone number. For the same reason, we cannot pick out your questions from all the others."],
    ["Niba wanditse amakuru bwite mu kibazo kandi ushaka ko dusiba icyo kibazo, tubwire icyo wanditse:", "If you wrote personal information in a question and want us to delete it, tell us what you wrote:"],
    ["Ntabwo amateka yabitswe kuri iki gikoresho.", "History could not be saved on this device."],
    ["Nta kiganiro kiraboneka.", "No conversations yet."],
    ["Nta kiganiro cyabonetse.", "No conversation found."],
    ["Siba iki kiganiro", "Delete this conversation"],
    ["Iki kiganiro kiraseswa kuri telefone yawe gusa. Kopi iri kuri seriveri ya Mfasha ntisibwa. Komeza?", "This conversation will be deleted from your phone only. The copy on the Mfasha server is not deleted. Continue?"],
    ["Ibiganiro byose biraseswa kuri telefone yawe gusa. Kopi ziri kuri seriveri ya Mfasha ntizisibwa. Komeza?", "All conversations will be deleted from your phone only. The copies on the Mfasha server are not deleted. Continue?"],
    ["Iki gisubizo nticyabitswe.", "This answer was not saved."],
    ["Ndimo gushaka igisubizo…", "Looking for an answer…"],
    ["Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.", "Your feedback was not saved. Please try again."],
    ["Murakoze ku gitekerezo cyanyu.", "Thank you for your feedback."],
    ["Iki gisubizo nticyizewe bihagije. Genzura n’andi makuru.", "This answer is not reliable enough. Check with other sources."],
    ["Genzura n’andi makuru kugira ngo wemeze iki gisubizo.", "Check other sources to confirm this answer."],
    ["Cyasuzumwe n’umukozi w’ubuhinzi", "Reviewed by an agricultural officer"],
    ["Ntikirasuzumwa n’umukozi w’ubuhinzi. Ntukishingikirize kuri cyo wenyine.", "Not yet reviewed by an agricultural officer. Do not rely on it alone."],
    ["Byamfashije", "It helped me"], ["Ntibyamfashije", "It did not help me"], ["Koporora", "Copy"],
    ["Iyi mushakisha ntishobora gukoporora.", "This browser cannot copy."],
    ["Igisubizo cyakoporowe.", "Answer copied."],
    ["Ntabwo igisubizo cyakoporowe.", "The answer could not be copied."],
    ["Ndimo gutegura amajwi yawe…", "Preparing your recording…"],
    ["Ntabwo amajwi yafashwe. Ongera ugerageze.", "The audio could not be recorded. Please try again."],
    ["Koresha uru rubuga kuri HTTPS cyangwa localhost kugira ngo ufungure mikoro.", "Use this site over HTTPS or localhost to turn on the microphone."],
    ["Iyi mushakisha ntishobora gufata amajwi.", "This browser cannot record audio."],
    ["Emera gukoresha mikoro nibigusabwa.", "Allow microphone use when asked."],
    ["Ntabwo amajwi yafashwe. Reba uruhushya rwa mikoro.", "The audio could not be recorded. Check microphone permission."],
    ["Nta majwi yafashwe. Ongera ugerageze.", "No audio was recorded. Please try again."],
    ["Ndimo kumva ibyo wavuze…", "Listening to what you said…"],
    ["Ntabwo amajwi yahinduwe inyandiko. Ongera ugerageze.", "Your speech could not be turned into text. Please try again."],
    ["Ntabwo amajwi yahinduwe inyandiko.", "Your speech could not be turned into text."],
    ["Ndakumva. Kanda “Rangiza” nurangiza kuvuga.", "I am listening. Tap “Finish” when you are done speaking."],
    ["Ntabwo nashoboye gukoresha mikoro. Reba uruhushya rwa mushakisha.", "I could not use the microphone. Check your browser permission."],
    ["Ikibazo kirenze inyuguti 500. Gabanya inyandiko mbere yo kohereza.", "Your question is over 500 characters. Shorten it before sending."],
    ["Habaye ikibazo mu gushaka igisubizo.", "There was a problem finding an answer."],
    ["Nta biganiro bihari byo gusiba.", "There are no conversations to delete."]
  ];
  var D = Object.create(null);
  PAIRS.forEach(function (p) { D[p[0]] = p[1]; });

  var P = [
    [/^Icyizere: (kinshi|giciriritse|gike)$/, function (m, t) { return 'Confidence: ' + { kinshi: 'high', giciriritse: 'medium', gike: 'low' }[t]; }],
    [/^Muraho, (.+)$/, 'Hello, $1'],
    [/^Byavuguruwe saa (.+)$/, 'Updated at $1'],
    [/^#(\d+) · (Cyoherejwe ku mukozi|Cyasubijwe)( · Cyasuzumwe)?$/, function (m, id, st, rv) { return '#' + id + ' · ' + (st === 'Cyasubijwe' ? 'Answered' : 'Referred to an officer') + (rv ? ' · Reviewed' : ''); }],
    [/^Igisubizo #(\d+)$/, 'Answer #$1'],
    [/^Ubwoko: (.+)$/, 'Category: $1'],
    [/^Amanota: (.+)$/, 'Score: $1'],
    [/^Inyandiko: (.+)$/, 'Passage: $1'],
    [/^Erekana ibindi \(hagaragara (\d+)(?: kuri (\d+))?\)$/, function (m, a, b) { return 'Show more (' + a + (b ? ' of ' + b : '') + ' shown)'; }],
    [/^Ikibazo ntikigaragara\. Gisuzume ukoresheje nimero #(\d+)\.$/, 'Question not available. Review it using number #$1.'],
    [/^Isuzuma ry’igisubizo #(\d+) ryabitswe\. Murakoze!(?: (.*))?$/, function (m, id, rest) { return 'Review of answer #' + id + ' saved. Thank you!' + (rest ? ' ' + T(rest) : ''); }]
  ];

  function norm(s) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); }
  function T(s) {
    if (!s) return s;
    var lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0], k = norm(s);
    if (!k) return s;
    if (D[k]) return lead + D[k] + trail;
    for (var i = 0; i < P.length; i++) if (P[i][0].test(k)) return lead + k.replace(P[i][0], P[i][1]) + trail;
    return s;
  }

  // confirm()/alert() boxes are not part of the page, so translate them here.
  ['confirm', 'alert'].forEach(function (n) { var o = window[n]; window[n] = function (m) { return o.call(window, lang === 'en' ? T(String(m)) : m); }; });

  /* Longer texts with links / lists are swapped as whole blocks. */
  var L = '<a href="#" data-doc="privacy">Privacy policy</a>', U = '<a href="#" data-doc="terms">Terms of use</a>';
  var EI = {
    legal: 'By signing in, you accept the ' + L + ' and the ' + U + '.',
    consent: 'I have read and accept the ' + L + ' and the ' + U + '.',
    privacy:
      '<p>This policy explains what information Mfasha collects, what it is used for and how it is protected. It is meant for agricultural officers who create an account. Last updated: November 2026.</p>' +
      '<h3>Information we collect</h3><ul>' +
      '<li><strong>When you create an account:</strong> your name and phone number.</li>' +
      '<li><strong>Your PIN:</strong> is not stored as you typed it. We store a scrambled version (a hash) from which the PIN cannot be recovered. We cannot see your PIN either.</li>' +
      '<li><strong>When you review an answer:</strong> your verdict (correct, partly correct or incorrect), whether it is relevant, clear and safe, anything you add, and your name.</li>' +
      '<li><strong>When you sign in:</strong> wrong PIN attempts are counted briefly on the server so the account can be locked. They are not kept permanently.</li></ul>' +
      '<p>Farmers do not create accounts. We do not collect their names or phone numbers. We store the question, the answer, the time and any feedback they give. When they speak, we store only a text transcript of what they said. The audio itself is not stored.</p>' +
      '<h3>What we use it for</h3><ul><li>To sign you in to your account.</li><li>To know which answers have been reviewed, and by whom.</li><li>To improve Mfasha’s answers.</li></ul>' +
      '<p>We do not sell your information and it is not used for advertising.</p>' +
      '<h3>Who can see your information</h3><p>Information is stored on the Mfasha server. Only authorised people can access it. A suspended account immediately loses access.</p>' +
      '<h3>How we protect it</h3><ul><li>Your PIN is stored as a scrambled value that does not reveal the PIN itself.</li><li>Five wrong PINs in a row lock the account for five minutes.</li><li>After you sign in, you are asked to sign in again after 12 hours.</li></ul>' +
      '<p>No method protects 100%. Do not give your PIN to anyone.</p>' +
      '<h3>How long we keep it</h3><p>We have not set a fixed period yet. When we do, we will state it here.</p>' +
      '<h3>Your rights</h3><p>You have the right to see, correct or delete your information, and to object to its use. This is based on Law No. 058/2021 on the protection of personal data and privacy in Rwanda. Ask your supervisor or the Mfasha manager. We may ask you to prove it is you before making changes.</p>' +
      '<h3>Changes to this policy</h3><p>If anything changes, we will let you know.</p>',
    terms:
      '<p>These terms govern how agricultural officers use Mfasha.</p>' +
      '<h3>Your account</h3><p>The account is yours. Do not give your PIN to anyone.</p>' +
      '<h3>Reviewing</h3><p>Review answers honestly, based on your agricultural knowledge. Your verdicts help improve Mfasha.</p>' +
      '<h3>Use</h3><p>Use Mfasha only for agricultural work. Do not try to access information that is not yours or to damage the service.</p>' +
      '<h3>Limits</h3><p>Mfasha gives basic information. It does not replace the advice of an agricultural officer or a veterinarian.</p>' +
      '<h3>Suspending an account</h3><p>An account that is misused may be suspended. These terms may change; if they do, we will let you know.</p>'
  };

  /* DOM translation */
  var ATTRS = ['placeholder', 'aria-label', 'title'];
  var DATA_SEL = '#r-question,#r-answer,.o-item b,.question > div,.answer-text,.history-item,#typing-question';
  var SAFE = { '(nta kibazo)': 1, 'Igisubizo ntikigaragara.': 1, 'Ijwi ryawe…': 1, 'Nta gisubizo cyagarutse.': 1, 'Ikiganiro gishya': 1 };

  function isData(n) {
    var p = n.parentElement;
    if (!p || !p.closest(DATA_SEL)) return false;
    var v = norm(n.nodeValue);
    return !(SAFE[v] || v.indexOf('Ikibazo ntikigaragara') === 0);
  }
  function doText(n) {
    if (!n || n.nodeType !== 3) return;
    var v = n.nodeValue;
    // If this node currently contains our English translation, keep the original Kinyarwanda.
    if (n.__en !== undefined && v === n.__en) return;
    n.__rw = v;
    n.__en = undefined;
    if (lang !== 'en' || isData(n)) return;
    var o = T(v);
    if (o !== v) {
      n.__en = o;
      n.nodeValue = o;
    }
  }
  function doAttr(el, a) {
    var v = el.getAttribute(a); if (v == null) return;
    var s = el.__a || (el.__a = {}), r = s[a];
    if (r && r.en !== undefined && v === r.en) return;
    r = s[a] = { rw: v, en: undefined };
    if (lang !== 'en') return;
    var o = T(v);
    if (o !== v) { r.en = o; el.setAttribute(a, o); }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 || /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(root.tagName)) return;
    var els = [root].concat([].slice.call(root.querySelectorAll('[placeholder],[aria-label],[title]')));
    els.forEach(function (el) { ATTRS.forEach(function (a) { if (el.hasAttribute(a)) doAttr(el, a); }); });
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { return /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(n.parentNode.tagName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; }
    }), n, list = [];
    while ((n = w.nextNode())) list.push(n);
    list.forEach(doText);
  }
  function restore(root) {
    if (root && root.nodeType === 3) {
      if (root.__en !== undefined && root.nodeValue === root.__en) {
        root.nodeValue = root.__rw;
        root.__en = undefined;
      }
      return;
    }
    if (!root || root.nodeType !== 1 && root.nodeType !== 9) return;
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), n, list = [];
    while ((n = w.nextNode())) list.push(n);
    list.forEach(function (t) {
      if (t.__en !== undefined && t.nodeValue === t.__en) {
        t.nodeValue = t.__rw;
        t.__en = undefined;
      }
    });
    var attrs = [];
    if (root.nodeType === 1 && root.matches && root.matches('[placeholder],[aria-label],[title]')) attrs.push(root);
    if (root.querySelectorAll) attrs = attrs.concat([].slice.call(root.querySelectorAll('[placeholder],[aria-label],[title]')));
    attrs.forEach(function (el) {
      ATTRS.forEach(function (a) {
        var r = el.__a && el.__a[a];
        if (r && r.en !== undefined && el.getAttribute(a) === r.en) {
          el.setAttribute(a, r.rw);
          r.en = undefined;
        }
      });
    });
  }
  function swapBlocks() {
    document.querySelectorAll('[data-ei]').forEach(function (el) {
      if (el.__rwHtml === undefined) el.__rwHtml = el.innerHTML;
      el.innerHTML = lang === 'en' ? EI[el.getAttribute('data-ei')] : el.__rwHtml;
    });
  }
  function labels() {
    document.documentElement.lang = lang === 'en' ? 'en' : 'rw';
    document.title = lang === 'en' ? T(rwTitle) : rwTitle;
    document.querySelectorAll('[data-lang-toggle]').forEach(function (b) {
      var s = b.querySelector('[data-lang-label]') || b; s.textContent = lang === 'en' ? 'Kinyarwanda' : 'English';
      b.setAttribute('aria-label', lang === 'en' ? 'Hindura ururimi: Kinyarwanda' : 'Change language: English');
    });
  }
  function set(next) {
    next = next === 'en' ? 'en' : 'rw';
    // Restore first so switching back and forth never translates translated text.
    restore(document.body);
    lang = next;
    try { localStorage.setItem(KEY, lang); } catch (e) {}
    swapBlocks();
    if (lang === 'en') walk(document.body);
    labels();
  }

  /* Pages without a language button (home, chat) get one automatically. */
  function injectButton() {
    if (document.querySelector('[data-lang-toggle]')) return;
    var css = document.createElement('style');
    css.textContent = '.mf-lang{display:inline-flex;align-items:center;gap:8px;cursor:pointer;line-height:1;font-family:inherit;transition:border-color .2s,color .2s}.mf-lang svg{width:18px;height:18px;flex:none}.mf-nav-right{display:flex;align-items:center;gap:12px}.mf-lang-float{position:absolute;z-index:3}.mf-lang-fixed{position:fixed;top:14px;right:14px;z-index:50}';
    document.head.appendChild(css);
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'mf-lang'; b.setAttribute('data-lang-toggle', '');
    b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/></svg><span data-lang-label>English</span>';
    var action = document.querySelector('.navbar .nav-action'), main = document.querySelector('main.main');
    if (action) {
      var wrap = document.createElement('div'); wrap.className = 'mf-nav-right';
      action.parentNode.insertBefore(wrap, action); wrap.appendChild(b); wrap.appendChild(action);
    } else if (main) { b.classList.add('mf-lang-float'); main.appendChild(b); }
    else { b.classList.add('mf-lang-fixed'); document.body.appendChild(b); }
  }

  if (document.body) {
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        if (m.type === 'characterData') doText(m.target);
        else if (m.type === 'attributes') doAttr(m.target, m.attributeName);
        else Array.prototype.forEach.call(m.addedNodes, walk);
      });
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-lang-toggle]');
    if (b) set(lang === 'en' ? 'rw' : 'en');
  });
  window.MfashaI18n = { t: T, set: set, lang: function () { return lang; } };

  injectButton();
  if (lang === 'en') set('en'); else labels();
}
// Works whether the script tag sits in <head> or at the end of <body>.
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mfashaI18nBoot); else mfashaI18nBoot();