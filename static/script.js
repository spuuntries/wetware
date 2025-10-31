var socket = io();
var connected = false;
var chatWindow = document.getElementById("chat_window");
var responseText = document.getElementById("response_text");
var sendButton = document.getElementById("send_button");
var currentTurn = document.getElementById("current_turn");
var maxTurns = document.getElementById("max_turns");
var progressCircle = document.getElementById("progress_circle");
var gameStatus = document.getElementById("game_status");
var personaInfo = document.getElementById("persona_info");
var personalityInfo = document.getElementById("personality_info");
var charCount = document.getElementById("char_count");
var mobileMenuToggle = document.getElementById("mobile_menu_toggle");
var sidebarOverlay = document.getElementById("sidebar_overlay");
var infoPanel = document.getElementById("info_panel");

// Mobile menu toggle
function toggleSidebar() {
  mobileMenuToggle.classList.toggle("active");
  sidebarOverlay.classList.toggle("active");
  infoPanel.classList.toggle("active");
  document.body.style.overflow = infoPanel.classList.contains("active")
    ? "hidden"
    : "";
}

mobileMenuToggle.addEventListener("click", toggleSidebar);
// sidebarOverlay.addEventListener('click', toggleSidebar);

// Close sidebar on window resize if open
window.addEventListener("resize", function () {
  if (window.innerWidth > 768 && infoPanel.classList.contains("active")) {
    toggleSidebar();
  }
});

// Character counter
responseText.addEventListener("input", function () {
  charCount.textContent = this.value.length;
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 150) + "px";
});

// Format timestamp
function getTimestamp() {
  const now = new Date();
  return now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function addMessage(text, type = "system", avatar = "⚡") {
  if (!text || !text.trim() || !text.length) {
    return;
  }
  var messageDiv = document.createElement("div");
  messageDiv.className = "message " + type;

  var avatarDiv = document.createElement("div");
  avatarDiv.className = "message-avatar";
  avatarDiv.innerText = avatar;

  var contentWrapper = document.createElement("div");
  contentWrapper.className = "message-content-wrapper";

  var contentDiv = document.createElement("div");
  contentDiv.className = "message-content";
  contentDiv.innerText = text;

  contentWrapper.appendChild(contentDiv);

  if (type === "user" || type === "bot") {
    var timestamp = document.createElement("div");
    timestamp.className = "message-timestamp";
    timestamp.innerText = getTimestamp();
    contentWrapper.appendChild(timestamp);
  }

  messageDiv.appendChild(avatarDiv);
  messageDiv.appendChild(contentWrapper);
  chatWindow.appendChild(messageDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function updateStatus(status, cls) {
  gameStatus.className = "status_badge " + cls;
  gameStatus.innerHTML =
    '<div class="status-indicator"></div><span>' + status + "</span>";
}

function updateProgress(current, max) {
  var percentage = current / max;
  var circumference = 2 * Math.PI * 62; // radius = 62
  var offset = circumference - percentage * circumference;
  progressCircle.style.strokeDashoffset = offset;
}

function celebrateWin() {
  // Confetti animation
  var duration = 3 * 1000;
  var animationEnd = Date.now() + duration;
  var defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 9999 };

  function randomInRange(min, max) {
    return Math.random() * (max - min) + min;
  }

  var interval = setInterval(function () {
    var timeLeft = animationEnd - Date.now();

    if (timeLeft <= 0) {
      return clearInterval(interval);
    }

    var particleCount = 50 * (timeLeft / duration);
    confetti(
      Object.assign({}, defaults, {
        particleCount,
        origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 },
      })
    );
    confetti(
      Object.assign({}, defaults, {
        particleCount,
        origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 },
      })
    );
  }, 250);
}

function updateHeaderStatus(status, cls) {
  var headerStatus = document.getElementById("connection_status");
  var headerStatusText = document.getElementById("connection_status_text");
  headerStatus.className = "connection-status " + cls;
  headerStatusText.innerText = status;
}

socket.on("connect", () => {
  addMessage(
    "Neural link established. Generating mission parameters...",
    "system",
    "⚡"
  );
  if (!connected) updateHeaderStatus("Connecting...", "connection_connecting");
});

socket.on("initial_mission", (msg) => {
  addMessage("Mission initialized. Client connected.", "system", "✓");
  addMessage(msg.first_message, "bot", "👤");

  // Parse persona info
  var personaParts = msg.persona.split("(Personality:");
  personaInfo.innerText = personaParts[0].trim();

  if (personaParts.length > 1) {
    personalityInfo.innerText = "🎭 " + personaParts[1].replace(")", "").trim();
    personalityInfo.style.display = "block";
  }

  currentTurn.innerText = "1";
  maxTurns.innerText = msg.max_turns;
  updateProgress(1, msg.max_turns);
  updateStatus("Active", "status_active");
  if (!connected) {
    updateHeaderStatus("Connected", "connection_connected");
    connected = true;
  }
  responseText.disabled = false;
  sendButton.disabled = false;
  responseText.focus();
});

socket.on("disconnect", () => {
  connected = false;
  updateHeaderStatus("Connecting...", "connection_connecting");
  updateStatus("Reconnecting...", "status_waiting");
});

socket.on("new_bot_message", (msg) => {
  // Remove typing indicator if exists
  var typingIndicator = chatWindow.querySelector(".typing-indicator");
  if (typingIndicator) {
    typingIndicator.parentElement.parentElement.remove();
  }

  addMessage(msg.message, "bot", "👤");
  currentTurn.innerText = msg.turn;
  updateProgress(msg.turn, msg.max_turns);
  updateStatus("Active", "status_active");
  responseText.disabled = false;
  sendButton.disabled = false;
  responseText.focus();
});

socket.on("game_over", (msg) => {
  // Remove typing indicator if exists
  var typingIndicator = chatWindow.querySelector(".typing-indicator");
  if (typingIndicator) {
    typingIndicator.parentElement.parentElement.remove();
  }

  if (msg.win) {
    addMessage("✓ Mission Complete", "win", "🎉");
    celebrateWin();
  } else {
    addMessage("✗ Mission Failed", "lose", "💥");
  }
  addMessage(msg.message, "bot", "👤");
  responseText.disabled = true;
  sendButton.disabled = true;
  addMessage("Refresh page to start new mission", "system", "🔄");
  updateStatus(
    msg.win ? "Success" : "Failed",
    msg.win ? "status_active" : "status_ended"
  );
});

function sendMessage() {
  var text = responseText.value.trim();
  if (!text) return;

  addMessage(text, "user", "🧑");
  socket.emit("player_message", { message: text });
  responseText.value = "";
  charCount.textContent = "0";
  responseText.style.height = "auto";
  responseText.disabled = true;
  sendButton.disabled = true;
  updateStatus("Processing...", "status_waiting");

  // Add typing indicator
  var typingIndicator = document.createElement("div");
  typingIndicator.className = "message bot";
  typingIndicator.innerHTML =
    '<div class="message-avatar">👤</div><div class="message-content-wrapper"><div class="message-content typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>';
  chatWindow.appendChild(typingIndicator);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

sendButton.onclick = sendMessage;
responseText.onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
};
