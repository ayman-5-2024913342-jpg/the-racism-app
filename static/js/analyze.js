(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const fileInput = $("file-input");
  const dropzone = $("dropzone");
  const uploadView = $("upload-view");
  const editorView = $("editor-view");
  const confirmedView = $("confirmed-view");
  const cropImage = $("crop-image");
  const status = $("status-message");
  const cameraModal = $("camera-modal");
  const video = $("camera-video");
  const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const maxBytes = Number(document.body.dataset.maxUploadMb || 10) * 1024 * 1024;
  let cropper = null;
  let activeStream = null;
  let lastSource = null;
  let confirmedBlob = null;
  let focusBeforeCamera = null;

  function showStatus(message, type = "error") {
    status.hidden = false;
    status.className = `status-message ${type}`;
    status.textContent = message;
  }
  function clearStatus() { status.hidden = true; status.textContent = ""; status.className = "status-message"; }
  function setStep(step) {
    document.querySelectorAll("[data-step-indicator]").forEach((node) => {
      const n = Number(node.dataset.stepIndicator);
      node.classList.toggle("current", n === step);
      node.classList.toggle("complete", n < step);
    });
  }
  async function api(url, options) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (e) {
      throw new Error("Couldn't reach the server. Check your connection and try again.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const err = new Error(data.detail || "Something went wrong. Please try again.");
      err.code = data.code;
      err.canOverride = Boolean(data.can_override);
      throw err;
    }
    return data;
  }
  function destroyCropper() { if (cropper) { cropper.destroy(); cropper = null; } }
  function showEditor(dataUrl) {
    clearStatus();
    uploadView.hidden = true;
    confirmedView.hidden = true;
    editorView.hidden = false;
    setStep(2);
    destroyCropper();
    cropImage.onload = () => {
      cropper = new Cropper(cropImage, {
        viewMode: 1, dragMode: "move", aspectRatio: NaN, autoCropArea: 0.78, responsive: true, restore: false,
        guides: true, center: true, highlight: true, background: false, movable: true, zoomable: true,
        zoomOnWheel: true, zoomOnTouch: true, rotatable: false, scalable: false,
        checkOrientation: false, toggleDragModeOnDblclick: false,
      });
    };
    cropImage.src = dataUrl;
  }
  function showUpload() {
    destroyCropper();
    confirmedBlob = null;
    editorView.hidden = true;
    confirmedView.hidden = true;
    uploadView.hidden = false;
    setStep(1);
    clearStatus();
    const skin = $("opt-skin");
    if (skin) skin.checked = false;
  }
  async function postImage(file) {
    if (!file) return;
    clearStatus();
    if (file.size > maxBytes) {
      showStatus(`That file is too large. Please choose an image under ${Math.round(maxBytes / 1024 / 1024)} MB.`);
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      showStatus("Please choose a JPEG, PNG, or WebP image.");
      return;
    }
    showStatus("Checking image content and preparing a safe preview…", "loading");
    const form = new FormData();
    form.append("file", file, file.name || "camera-photo.jpg");
    try {
      const data = await api("/api/upload", { method: "POST", body: form, headers: { "X-CSRF-Token": csrf } });
      lastSource = data.image_data_url;
      showEditor(data.image_data_url);
    } catch (error) {
      showStatus(error.message || "Upload failed. Please try again.");
    }
  }
  $("choose-file").addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    fileInput.click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    postImage(file);
    fileInput.value = "";
  });
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault(); dropzone.classList.remove("dragging");
  }));
  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) postImage(file);
  });

  $("zoom-in").addEventListener("click", () => cropper && cropper.zoom(0.1));
  $("zoom-out").addEventListener("click", () => cropper && cropper.zoom(-0.1));
  $("reset-crop").addEventListener("click", () => cropper && cropper.reset());
  $("replace-image").addEventListener("click", () => fileInput.click());
  $("back-to-upload").addEventListener("click", showUpload);
  $("edit-again").addEventListener("click", () => showEditor(lastSource));
  $("start-over").addEventListener("click", showUpload);

  // Keyboard-accessible crop movement while the crop stage has focus.
  document.querySelector(".crop-stage").addEventListener("keydown", (event) => {
    if (!cropper) return;
    const step = event.shiftKey ? 20 : 6;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[event.key]) { event.preventDefault(); cropper.move(...moves[event.key]); }
    if (event.key === "+" || event.key === "=") cropper.zoom(0.1);
    if (event.key === "-") cropper.zoom(-0.1);
  });
  document.querySelector(".crop-stage").setAttribute("tabindex", "0");

  $("confirm-crop").addEventListener("click", async () => {
    if (!cropper) return;
    clearStatus();
    const button = $("confirm-crop");
    button.disabled = true;
    button.textContent = "Checking crop…";
    try {
      // The crop is sent losslessly (PNG) so that no extra compression shifts the measured colors.
      const canvas = cropper.getCroppedCanvas({
        maxWidth: 1200, maxHeight: 1200, fillColor: "#f8f7f2", imageSmoothingEnabled: true, imageSmoothingQuality: "high",
      });
      if (!canvas || canvas.width < 32 || canvas.height < 32) throw new Error("Please select a larger crop.");
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("The browser couldn't create this crop. Please try again.");
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Could not read the selected crop."));
        reader.readAsDataURL(blob);
      });
      const data = await api("/api/confirm-crop", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ image_data_url: dataUrl }),
      });
      confirmedBlob = blob;
      destroyCropper();
      editorView.hidden = true;
      confirmedView.hidden = false;
      $("confirmed-image").src = data.image_data_url;
      $("confirmed-message").textContent = data.message;
      $("confirmed-meta").textContent = `${data.width} × ${data.height} px preview · not saved`;
      setStep(3);
    } catch (error) {
      showStatus(error.message || "Could not confirm crop.");
    } finally {
      button.disabled = false;
      button.innerHTML = 'Confirm crop <span>→</span>';
    }
  });

  $("run-analysis").addEventListener("click", async () => {
    if (!confirmedBlob) return;
    clearStatus();
    const nameInput = $("user-name");
    const name = nameInput.value.trim();
    if (!name) {
      showStatus("Please enter your name before analyzing.");
      nameInput.focus();
      return;
    }
    const button = $("run-analysis");
    button.disabled = true;
    button.textContent = "Analyzing…";
    showStatus("Analyzing your crop. This usually takes a second or two…", "loading");
    const form = new FormData();
    form.append("file", confirmedBlob, "crop.png");
    form.append("treat_as_skin", $("opt-skin").checked ? "true" : "false");
    form.append("save", $("opt-save").checked ? "true" : "false");
    form.append("name", name);
    try {
      const data = await api("/api/analyze", { method: "POST", body: form, headers: { "X-CSRF-Token": csrf } });
      window.location.assign(data.result_url);
    } catch (error) {
      showStatus(error.message || "The analysis failed. Please try again.");
      if (error.canOverride) {
        $("advanced").open = true;
        $("opt-skin").focus();
      }
      button.disabled = false;
      button.innerHTML = 'Analyze this crop <span>→</span>';
    }
  });

  async function stopCamera() {
    if (activeStream) activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
    video.srcObject = null;
    cameraModal.hidden = true;
    if (focusBeforeCamera) focusBeforeCamera.focus();
  }
  async function openCamera() {
    focusBeforeCamera = document.activeElement;
    cameraModal.hidden = false;
    $("camera-help").textContent = "Requesting camera permission…";
    $("capture-photo").disabled = true;
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("This browser doesn't offer camera access here. Try localhost or HTTPS, or upload a photo instead.");
      }
      activeStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "user" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      video.srcObject = activeStream;
      await video.play();
      $("camera-help").textContent = "Use soft, even light and keep your face comfortably in frame.";
      $("capture-photo").disabled = false;
      $("capture-photo").focus();
    } catch (error) {
      $("camera-help").textContent = error.name === "NotAllowedError"
        ? "Camera permission was denied. Allow access in your browser settings, or upload a photo instead."
        : (error.message || "Camera couldn't be opened. Upload a photo instead.");
      $("capture-photo").disabled = true;
    }
  }
  $("open-camera").addEventListener("click", openCamera);
  $("close-camera").addEventListener("click", stopCamera);
  $("cancel-camera").addEventListener("click", stopCamera);
  cameraModal.addEventListener("click", (event) => { if (event.target === cameraModal) stopCamera(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !cameraModal.hidden) stopCamera();
  });
  $("capture-photo").addEventListener("click", async () => {
    if (!video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 3000 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    await stopCamera();
    if (blob) {
      const file = new File([blob], "camera-photo.jpg", { type: "image/jpeg" });
      await postImage(file);
    } else showStatus("Couldn't capture that photo. Please try again.");
  });

  // "Take a photo" on the landing page links to /analyze#camera
  if (window.location.hash === "#camera") openCamera();
})();
