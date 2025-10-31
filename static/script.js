var socket = io();
var connected = false;
var hasActiveGame = false;
var currentGameState = null; // Store game state
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
  if (!connected) {
    addMessage(
      "Neural link established. Standby...",
      "system",
      "⚡"
    );
    updateHeaderStatus("Connecting...", "connection_connecting");
    // New client - tell server we don't have a game
    socket.emit("client_has_game", { hasGame: false });
  } else {
    addMessage("Connection restored.", "system", "✓");
    updateHeaderStatus("Connected", "connection_connected");
    updateStatus("Active", "status_active");
    responseText.disabled = false;
    sendButton.disabled = false;
    // Reconnecting client - send game state if we have one
    if (hasActiveGame && currentGameState) {
      socket.emit("client_has_game", { 
        hasGame: true,
        gameState: currentGameState
      });
    } else {
      socket.emit("client_has_game", { hasGame: false });
    }
  }
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
  updateHeaderStatus("Connected", "connection_connected");
  connected = true;
  hasActiveGame = true;
  
  // Store game state
  currentGameState = {
    persona: msg.persona,
    technical_goal: msg.technical_goal,
    personality_trait: msg.personality_trait,
    turn_count: 0,
    max_turns: msg.max_turns
  };
  
  responseText.disabled = false;
  sendButton.disabled = false;
  responseText.focus();
});

socket.on("resume_mission", (msg) => {
  // Don't add any messages - just restore UI state
  console.log("Resuming mission - restoring UI state only");

  // Parse persona info
  var personaParts = msg.persona.split("(Personality:");
  personaInfo.innerText = personaParts[0].trim();

  if (personaParts.length > 1) {
    personalityInfo.innerText = "🎭 " + personaParts[1].replace(")", "").trim();
    personalityInfo.style.display = "block";
  }

  currentTurn.innerText = msg.current_turn;
  maxTurns.innerText = msg.max_turns;
  updateProgress(msg.current_turn, msg.max_turns);
  updateStatus("Active", "status_active");
  updateHeaderStatus("Connected", "connection_connected");
  connected = true;
  hasActiveGame = true;
  responseText.disabled = false;
  sendButton.disabled = false;
  responseText.focus();
});

socket.on("session_restored", () => {
  // Server successfully restored session from our game state
  console.log("Server restored session from client state");
  updateHeaderStatus("Connected", "connection_connected");
  updateStatus("Active", "status_active");
  responseText.disabled = false;
  sendButton.disabled = false;
  responseText.focus();
});

socket.on("server_lost_session", () => {
  // Server lost our session and can't continue the game
  console.log("Server lost session - need to refresh");
  addMessage("⚠️ Server restarted and lost game state", "system", "⚠️");
  addMessage("Please refresh the page to start a new mission", "system", "🔄");
  updateStatus("Session Lost", "status_ended");
  responseText.disabled = true;
  sendButton.disabled = true;
  hasActiveGame = false;
  currentGameState = null;
});

socket.on("server_requests_new_game", () => {
  // Server lost our session, needs us to start fresh
  console.log("Server lost session, starting new game");
  hasActiveGame = false;
  currentGameState = null;
  // Server will send initial_mission next
});

socket.on("disconnect", () => {
  updateHeaderStatus("Reconnecting...", "connection_connecting");
  updateStatus("Reconnecting...", "status_waiting");
  responseText.disabled = true;
  sendButton.disabled = true;
});

socket.on("new_bot_message", (msg) => {
  // Remove typing indicator if exists
  var typingIndicator = chatWindow.querySelector(".typing-indicator");
  if (typingIndicator) {
    typingIndicator.parentElement.parentElement.remove();
  }

  addMessage(msg.message, "bot", "👤");
  currentTurn.innerText = msg.turn;
  maxTurns.innerText = msg.max_turns;
  updateProgress(msg.turn, msg.max_turns);
  updateStatus("Active", "status_active");
  
  // Update stored turn count
  if (currentGameState) {
    currentGameState.turn_count = msg.turn - 1;
  }
  
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
  hasActiveGame = false;
  currentGameState = null;
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
