window.onerror = function(msg, url, line) {
  var errStr = 'Err L' + line + ': ' + msg;
  var el = document.getElementById('overlay-status');
  if (el) el.innerHTML = '<span style="color:#ff5252;">' + errStr + '</span>';
  try {
    var xhr = new XMLHttpRequest({ mozSystem: true });
    xhr.open('GET', 'http://192.168.1.15:8000/api/camera/log?msg=' + encodeURIComponent(errStr), true);
    xhr.send();
  } catch(e) {}
};

var v, c, st, camName;
var streaming = false, frameCount = 0, currentCamera = 0, mozCam = null;
var screenOff = false, wakeLock = null, targetUploadIntervalMs = 2000;
var UPLOAD_URLS = [
  'http://192.168.1.15:8000/api/camera/upload',
  'http://127.0.0.1:8000/api/camera/upload'
];
var activeUploadUrl = UPLOAD_URLS[0];

// Request CPU wake lock so camera continues streaming even if screen is turned OFF!
if (navigator.requestWakeLock) {
  try {
    wakeLock = navigator.requestWakeLock('cpu');
  } catch(e) {}
}

function logStatus(msg) {
  if (st) st.innerHTML = msg;
  try {
    var xhr = new XMLHttpRequest({ mozSystem: true });
    xhr.open('GET', 'http://192.168.1.15:8000/api/camera/log?msg=' + encodeURIComponent(msg.replace(/<[^>]*>?/gm, '')), true);
    xhr.send();
  } catch(e) {}
}

function toggleScreen(forceOff) {
  if (navigator.mozPower) {
    if (typeof forceOff === 'boolean') {
      screenOff = forceOff;
    } else {
      screenOff = !screenOff;
    }
    navigator.mozPower.screenEnabled = !screenOff;
    try {
      if ('screenBrightness' in navigator.mozPower) {
        navigator.mozPower.screenBrightness = screenOff ? 0.0 : 0.5;
      }
    } catch(e) {}
    logStatus(screenOff ? 'Screen OFF (Streaming in Background)' : 'Screen ON');
  } else {
    logStatus('mozPower not available');
  }
}

// Poll server for remote screen toggle commands from PC Dashboard
function pollScreenCmd() {
  try {
    var xhr = new XMLHttpRequest({ mozSystem: true });
    xhr.open('GET', 'http://192.168.1.15:8000/api/camera/screen_cmd?t=' + Date.now(), true);
    xhr.timeout = 1000;
    xhr.onload = function() {
      if (xhr.status === 200 && xhr.responseText) {
        try {
          var res = JSON.parse(xhr.responseText);
          if (res.cmd === 'off' && !screenOff) {
            toggleScreen(true);
          } else if (res.cmd === 'on' && screenOff) {
            toggleScreen(false);
          }
          if (res.interval_ms) {
            targetUploadIntervalMs = Math.max(30, parseInt(res.interval_ms, 10));
          }
        } catch(e) {}
      }
      setTimeout(pollScreenCmd, 5000);
    };
    xhr.onerror = function() { setTimeout(pollScreenCmd, 5000); };
    xhr.ontimeout = function() { setTimeout(pollScreenCmd, 5000); };
    xhr.send();
  } catch(e) {
    setTimeout(pollScreenCmd, 5000);
  }
}

function startCamera(which) {
  logStatus('Selecting camera ' + which + '...');
  if (mozCam) {
    try { mozCam.release(); } catch(e) {}
    mozCam = null;
  }

  // Method 1: Native mozCameras (Qualcomm ISP driver)
  if (navigator.mozCameras) {
    try {
      var cameraList = navigator.mozCameras.getListOfCameras();
      var target = (cameraList && cameraList.length > which) ? cameraList[which] : (cameraList && cameraList[0]) ? cameraList[0] : '0';
      if (camName) camName.textContent = (target.indexOf('1') !== -1 || which === 1) ? 'Front' : 'Rear';
      logStatus('Requesting mozCamera (' + target + ')...');

      navigator.mozCameras.getCamera(target, { mode: 'picture' })
        .then(function(params) {
          logStatus('Camera acquired! Binding stream...');
          mozCam = params.camera;
          v.mozSrcObject = mozCam;
          v.play();
          streaming = true;
          logStatus('<span class="pulse">● Live Streaming Active!</span>');
          sendLoop();
        })
        .catch(function(err) {
          logStatus('mozCameras error: ' + err + '. Trying WebRTC...');
          startWebRTC(which);
        });
      return;
    } catch(e) {
      logStatus('mozCameras exception: ' + e + '. Trying WebRTC...');
    }
  }

  startWebRTC(which);
}

function startWebRTC(which) {
  var mode = (which === 1 ? 'user' : 'environment');
  if (camName) camName.textContent = (which === 1 ? 'Front' : 'Rear');
  var constraints = {
    video: { facingMode: mode, width: { ideal: 320 }, height: { ideal: 240 } },
    audio: false
  };

  var p = null;
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    p = navigator.mediaDevices.getUserMedia(constraints);
  } else if (navigator.mozGetUserMedia) {
    p = new Promise(function(resolve, reject) {
      navigator.mozGetUserMedia(constraints, resolve, function(err) {
        navigator.mozGetUserMedia({ video: true, audio: false }, resolve, reject);
      });
    });
  }

  if (p) {
    p.then(function(stream) {
      try { v.srcObject = stream; } catch(e) { v.src = URL.createObjectURL(stream); }
      if (!v.srcObject && window.URL) v.src = URL.createObjectURL(stream);
      v.play();
      streaming = true;
      logStatus('<span class="pulse">● Live Streaming (WebRTC)!</span>');
      sendLoop();
    }).catch(function(e) {
      logStatus('Camera Error: ' + (e.name || e.message || e));
    });
  } else {
    logStatus('No camera API supported on this device');
  }
}

// Dynamic Frame Dispatcher
function sendLoop() {
  if (!streaming) return;
  try {
    var w = Math.min(v.videoWidth || 320, 320);
    var h = Math.min(v.videoHeight || 240, 240);
    c.width = w;
    c.height = h;
    var ctx = c.getContext('2d');
    ctx.drawImage(v, 0, 0, w, h);
    c.toBlob(function(blob) {
      if (blob) {
        var xhr = new XMLHttpRequest({ mozSystem: true });
        xhr.open('POST', activeUploadUrl, true);
        xhr.timeout = Math.max(1500, targetUploadIntervalMs + 1000);
        xhr.onload = function() {
          frameCount++;
          if (st && !screenOff) {
            st.innerHTML = '<span class="pulse">● Live! (' + frameCount + ' frames)</span>';
          }
          try {
            var resp = JSON.parse(xhr.responseText);
            if (resp && resp.interval_ms) {
              targetUploadIntervalMs = Math.max(30, parseInt(resp.interval_ms, 10));
            }
            if (resp && resp.cmd) {
              if (resp.cmd === 'off' && !screenOff) {
                toggleScreen(true);
              } else if (resp.cmd === 'on' && screenOff) {
                toggleScreen(false);
              }
            }
          } catch(e) {}
          setTimeout(sendLoop, targetUploadIntervalMs);
        };
        xhr.onerror = function() {
          activeUploadUrl = (activeUploadUrl === UPLOAD_URLS[0]) ? UPLOAD_URLS[1] : UPLOAD_URLS[0];
          setTimeout(sendLoop, Math.max(200, targetUploadIntervalMs));
        };
        xhr.ontimeout = function() { setTimeout(sendLoop, Math.max(200, targetUploadIntervalMs)); };
        xhr.send(blob);
      } else {
        setTimeout(sendLoop, targetUploadIntervalMs);
      }
    }, 'image/jpeg', 0.40);
  } catch(e) {
    setTimeout(sendLoop, Math.max(200, targetUploadIntervalMs));
  }
}

// Physical Keypad Listener
window.addEventListener('keydown', function(e) {
  if (e.key === 'SoftLeft' || e.keyCode === 510) {
    currentCamera = (currentCamera === 0) ? 1 : 0;
    startCamera(currentCamera);
  } else if (e.key === 'Enter' || e.keyCode === 28) {
    streaming = !streaming;
    if (streaming) sendLoop();
    logStatus(streaming ? 'Resumed' : 'Paused');
  } else if (e.key === '0' || e.keyCode === 11 || e.key === '*' || e.keyCode === 227) {
    // Key 0 or Key * toggles physical screen blackout on the phone!
    toggleScreen();
  } else if (e.key === 'SoftRight' || e.keyCode === 511 || e.key === 'EndCall' || e.keyCode === 116) {
    if (mozCam) {
      try { mozCam.release(); } catch(e) {}
    }
    if (wakeLock) {
      try { wakeLock.unlock(); } catch(e) {}
    }
    window.close();
  }
});

function init() {
  v = document.getElementById('v');
  c = document.getElementById('c');
  st = document.getElementById('overlay-status');
  camName = document.getElementById('cam-name');
  logStatus('Hardware engine initializing...');
  setTimeout(function() {
    startCamera(0);
    pollScreenCmd();
  }, 250);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
