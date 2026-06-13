let mediaRecorder = null;
let chunks = [];
let stream = null;
let timerInterval = null;
let seconds = 0;
let audioCtx = null, analyser = null, animFrame = null;
let selectedDeviceId = null;
let selectedDeviceLabel = "mic";

// ── Load all audio input devices (including bluetooth) ──────────────────────
async function loadDevices() {
  try {
    // Must request permission first so labels are visible
    const tmp = await navigator.mediaDevices.getUserMedia({ audio: true });
    tmp.getTracks().forEach(t => t.stop());

    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter(d => d.kind === "audioinput");

    const sel = document.getElementById("deviceSelect");
    sel.innerHTML = "";

    if (!audioInputs.length) {
      sel.innerHTML = '<option value="">No audio devices found</option>';
      return;
    }

    // Add "System Audio" option via getDisplayMedia if supported
    const sysOpt = document.createElement("option");
    sysOpt.value = "__system__";
    sysOpt.textContent = "🖥️ System / Website Audio (tab capture)";
    sel.appendChild(sysOpt);

    audioInputs.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.textContent = (d.label || `Microphone (${d.deviceId.slice(0,8)})`) + (d.label?.toLowerCase().includes("bluetooth") ? " 🔵" : "");
      sel.appendChild(opt);
    });

    sel.onchange = () => {
      selectedDeviceId = sel.value;
      selectedDeviceLabel = sel.options[sel.selectedIndex].textContent.replace(/[^\w\s-]/g, "").trim().slice(0, 30);
    };
    sel.dispatchEvent(new Event("change"));
  } catch (e) {
    setStatus("❌ mic permission denied: " + e.message);
  }
}

// ── Get the right stream based on selection ──────────────────────────────────
async function getStream() {
  const sel = document.getElementById("deviceSelect");
  const val = sel.value;

  if (val === "__system__") {
    // Must request video:true — video:false is unsupported in most embedded browsers
    // We grab the stream, extract only audio tracks, video is ignored
    const displayStream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 1 },   // minimal video just to get the picker to open
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        sampleRate: 44100,
        channelCount: 2
      }
    });

    // Stop video tracks immediately — we only want audio
    displayStream.getVideoTracks().forEach(t => t.stop());

    const audioTracks = displayStream.getAudioTracks();
    if (!audioTracks.length) {
      throw new Error(
        "No audio track captured.\n\nWhen the screen picker opens:\n• Select a Chrome/Edge tab\n• Make sure 'Share tab audio' checkbox is ticked ✅\n• Or pick 'Entire screen' and enable 'Share system audio'"
      );
    }

    selectedDeviceLabel = "system_audio";
    // Return a new stream with only audio tracks
    return new MediaStream(audioTracks);
  } else {
    return await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: val ? { exact: val } : undefined,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        sampleRate: 44100,
        channelCount: 2
      }
    });
  }
}

// ── Toggle Record ────────────────────────────────────────────────────────────
async function toggleRecord() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    stopRecording();
  } else {
    startRecording();
  }
}

async function startRecording() {
  try {
    stream = await getStream();
    setupVisualizer(stream);

    const mimeType = getSupportedMime();
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    chunks = [];

    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.onstop = saveRecording;
    mediaRecorder.start(250);

    seconds = 0;
    timerInterval = setInterval(() => {
      seconds++;
      const m = String(Math.floor(seconds / 60)).padStart(2, "0");
      const s = String(seconds % 60).padStart(2, "0");
      document.getElementById("timer").textContent = `${m}:${s}`;
    }, 1000);

    const btn = document.getElementById("recordBtn");
    btn.classList.add("recording");     
    btn.innerHTML = `<span class="dot"></span> STOP RECORDING`;
    setStatus("🔴 recording — " + (selectedDeviceLabel || "audio"));
  } catch (e) {
    // Show full message — important for the "share tab audio" hint
    setStatus("❌ " + e.message.split("\n")[0]);
    if (e.message.includes("\n")) alert(e.message);
  }
}

function stopRecording() {
  if (mediaRecorder) mediaRecorder.stop();
  if (stream) stream.getTracks().forEach(t => t.stop());
  clearInterval(timerInterval);
  cancelAnimationFrame(animFrame);
  if (audioCtx) { audioCtx.close(); audioCtx = null; }

  const btn = document.getElementById("recordBtn");
  btn.classList.remove("recording");
  btn.innerHTML = `<span class="dot"></span> START RECORDING`;
  setStatus("⏳ saving mp3...");
}

async function saveRecording() {
  const blob = new Blob(chunks, { type: mediaRecorder.mimeType });
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  form.append("device", selectedDeviceLabel);

  try {
    const res = await fetch("/save-audio", { method: "POST", body: form });
    const data = await res.json();
    if (data.success) {
      setStatus("✅ saved → " + data.path.split(/[\\/]/).pop());
      loadRecordings();
    } else {
      setStatus("❌ " + data.error);
    }
  } catch (e) {
    setStatus("❌ upload failed: " + e.message);
  }
}

// ── Visualizer ───────────────────────────────────────────────────────────────
function setupVisualizer(stream) {
  audioCtx = new AudioContext();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 128;
  const src = audioCtx.createMediaStreamSource(stream);
  src.connect(analyser);
  drawViz();
}

function drawViz() {
  const canvas = document.getElementById("viz");
  const ctx = canvas.getContext("2d");
  const data = new Uint8Array(analyser.frequencyBinCount);

  function frame() {
    animFrame = requestAnimationFrame(frame);
    analyser.getByteFrequencyData(data);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const barW = canvas.width / data.length;
    data.forEach((v, i) => {
      const h = (v / 255) * canvas.height;
      const x = i * barW;
      ctx.fillStyle = `hsl(${70 + i * 1.2}, 100%, 55%)`;
      ctx.fillRect(x, canvas.height - h, barW - 1, h);
    });
  }
  frame();
}

// ── Recordings List ───────────────────────────────────────────────────────────
async function loadRecordings() {
  const res = await fetch("/recordings");
  const files = await res.json();
  const list = document.getElementById("recList");

  if (!files.length) {
    list.innerHTML = '<div class="empty">no recordings yet</div>';
    return;
  }

  list.innerHTML = files.map(f => `
    <div class="rec-item" id="item-${f}">
      <div class="rec-name" title="${f}">${f}</div>
      <audio controls src="/play/${encodeURIComponent(f)}" preload="none"></audio>
      <button class="btn-del" onclick="deleteRec('${f}')" title="delete">✕</button>
    </div>
  `).join("");
}

async function deleteRec(filename) {
  await fetch(`/delete/${encodeURIComponent(filename)}`, { method: "DELETE" });
  loadRecordings();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function getSupportedMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  return types.find(t => MediaRecorder.isTypeSupported(t)) || "";
}

function setStatus(msg) {
  document.getElementById("status").textContent = msg;
}

// Init
loadDevices();
loadRecordings();
