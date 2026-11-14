// The only JavaScript in the project. Pages work without it; this adds
// three small conveniences in the browser:
//
//   1. tap a highlighted word or name to see whose it is
//   2. open the story automatically when it has been written,
//      and say so when it has grown
//   3. the "Invite friends" / "Copy link" / "Share card" buttons

// ---- 1. whose word is this? ----

const credit = document.getElementById('credit');
let picked = null;

function pick(mark) {
  if (picked) picked.classList.remove('picked');
  picked = mark;
  mark.classList.add('picked');
  credit.textContent = mark.dataset.credit;
  credit.classList.add('on');
}

for (const mark of document.querySelectorAll('mark[data-credit]')) {
  mark.addEventListener('click', () => pick(mark));
  mark.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      pick(mark);
    }
  });
}

// ---- 2. watch for the story ----

const { poll, statusUrl, version } = document.body.dataset;

async function check() {
  try {
    const res = await fetch(statusUrl, { cache: 'no-store', headers: { accept: 'application/json' } });
    return res.ok ? await res.json() : null;
  } catch {
    return null; // offline for a moment; try again next time
  }
}

if (poll === 'writing') {
  let tries = 0;
  const timer = setInterval(async () => {
    const status = await check();
    if (status && status.phase === 'story') {
      clearInterval(timer);
      location.reload();
    }
    if (++tries === 12) document.getElementById('slow').hidden = false;
  }, 2500);
}

if (poll === 'growing') {
  const timer = setInterval(async () => {
    const status = await check();
    if (status && status.phase === 'story' && status.version > Number(version)) {
      clearInterval(timer);
      location.reload();
    }
  }, 5000);
}

// ---- 3. share ----

const shareText = "Add a few words to today's story";

// Sharing the card picture works on phones; elsewhere this returns false.
async function shareImage(imageUrl, url) {
  try {
    const blob = await (await fetch(imageUrl)).blob();
    const file = new File([blob], 'story-board.png', { type: 'image/png' });
    if (!navigator.canShare || !navigator.canShare({ files: [file] })) return false;
    await navigator.share({ files: [file], text: shareText, url });
    return true;
  } catch (err) {
    return err.name === 'AbortError'; // share sheet closed: nothing more to do
  }
}

for (const button of document.querySelectorAll('[data-share]')) {
  button.addEventListener('click', async () => {
    const { share: url, shareImage: imageUrl } = button.dataset;
    if (imageUrl && (await shareImage(imageUrl, url))) return;
    try {
      if (navigator.share) {
        await navigator.share({ title: document.title, text: shareText, url });
      } else {
        await navigator.clipboard.writeText(url);
        button.textContent = 'Link copied!';
      }
    } catch {
      /* share sheet closed */
    }
  });
}

// Update participant counts while an invited friend fills in their answers.
if (poll === 'form') {
  setInterval(async () => {
    const status = await check();
    const count = document.getElementById('participant-count');
    if (status && count) count.textContent = `${status.people} of ${count.dataset.limit} friends have joined today.`;
    if (status && status.phase !== 'form') location.reload();
  }, 5000);
}
