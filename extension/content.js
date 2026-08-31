// TG Private Video Downloader - Content Script for web.telegram.org

console.log("[TG Downloader] Content script active on Telegram Web.");

async function downloadVideoDirectly(videoEl, btnElement) {
  const originalHtml = btnElement.innerHTML;
  btnElement.innerHTML = "<span>Extracting MP4...</span>";
  btnElement.disabled = true;

  let src = videoEl ? (videoEl.src || videoEl.currentSrc) : null;
  if (!src && videoEl) {
    const sourceTag = videoEl.querySelector("source");
    if (sourceTag) src = sourceTag.src;
  }

  if (!src) {
    // Look for parent video element
    const parent = btnElement.parentElement;
    if (parent) {
      const v = parent.querySelector("video");
      if (v) src = v.src || v.currentSrc || (v.querySelector("source") ? v.querySelector("source").src : null);
    }
  }

  if (!src || src.startsWith("data:")) {
    alert("[TG Downloader] Please click play on the video first to load the stream, then click Download HD.");
    btnElement.innerHTML = originalHtml;
    btnElement.disabled = false;
    return;
  }

  const filename = `Telegram_Video_${Date.now()}.mp4`;

  try {
    // Fetch blob data directly inside tab context with session credentials
    const response = await fetch(src, { credentials: 'include' });
    if (!response.ok) throw new Error("HTTP error " + response.status);

    const rawBlob = await response.blob();
    
    // Explicitly enforce video/mp4 MIME type to prevent .htm extension
    const mp4Blob = new Blob([rawBlob], { type: "video/mp4" });
    const objectUrl = URL.createObjectURL(mp4Blob);

    // Create & click download link in tab DOM
    const link = document.createElement("a");
    link.style.display = "none";
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
      link.remove();
      URL.revokeObjectURL(objectUrl);
    }, 3000);

    btnElement.innerHTML = "<span>Saved MP4!</span>";
    setTimeout(() => {
      btnElement.innerHTML = originalHtml;
      btnElement.disabled = false;
    }, 2500);

  } catch (err) {
    console.warn("[TG Downloader] Direct tab fetch error, opening stream URL:", err);
    btnElement.innerHTML = "<span>Opening Stream...</span>";
    
    // Fallback: Open media URL directly in new window
    window.open(src, "_blank");

    setTimeout(() => {
      btnElement.innerHTML = originalHtml;
      btnElement.disabled = false;
    }, 2000);
  }
}

function injectDownloadButtons() {
  const videoContainers = document.querySelectorAll(
    ".media-widget-video, .video-player, .message-media-video, .media-container, .Bubble .video-wrapper, .tgme_widget_message_video_player, video"
  );

  videoContainers.forEach((container) => {
    const parent = container.tagName === "VIDEO" ? container.parentElement : container;
    if (!parent || parent.querySelector(".tg-ext-download-btn")) return;

    const videoEl = container.tagName === "VIDEO" ? container : container.querySelector("video");
    
    const btn = document.createElement("button");
    btn.className = "tg-ext-download-btn";
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
      </svg>
      <span>Download HD</span>
    `;

    btn.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      downloadVideoDirectly(videoEl, btn);
    };

    if (getComputedStyle(parent).position === "static") {
      parent.style.position = "relative";
    }

    parent.appendChild(btn);
  });
}

// Observe DOM changes on Telegram Web
const observer = new MutationObserver(() => { injectDownloadButtons(); });
observer.observe(document.body, { childList: true, subtree: true });
setInterval(injectDownloadButtons, 2000);
