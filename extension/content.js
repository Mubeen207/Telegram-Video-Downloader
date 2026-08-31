// TG Private Video Downloader - Content Script for web.telegram.org

console.log("[TG Downloader] Content script active on Telegram Web.");

async function handleVideoDownload(videoSrc, btnElement) {
  if (!videoSrc) {
    alert("[TG Downloader] Please click play on the video first to load the stream, then click Download HD.");
    return;
  }

  const originalHtml = btnElement.innerHTML;
  btnElement.innerHTML = "<span>Fetching...</span>";
  btnElement.disabled = true;

  const filename = `Telegram_Video_${Date.now()}.mp4`;

  try {
    // Strategy A: Fetch blob/stream directly in page context
    const res = await fetch(videoSrc);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.style.display = "none";
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    
    setTimeout(() => {
      a.remove();
      URL.revokeObjectURL(blobUrl);
    }, 2000);

    btnElement.innerHTML = "<span>Saved!</span>";
    setTimeout(() => {
      btnElement.innerHTML = originalHtml;
      btnElement.disabled = false;
    }, 2500);

  } catch (err) {
    console.warn("[TG Downloader] Direct blob fetch failed, falling back to background downloader...", err);
    
    // Strategy B: Send to background service worker with forced filename
    chrome.runtime.sendMessage(
      { action: "download_video", videoUrl: videoSrc, filename: filename },
      (response) => {
        btnElement.disabled = false;
        if (response && response.success) {
          btnElement.innerHTML = "<span>Downloading...</span>";
          setTimeout(() => { btnElement.innerHTML = originalHtml; }, 3000);
        } else {
          // Final Fallback: Open media URL directly in new tab
          window.open(videoSrc, "_blank");
          btnElement.innerHTML = originalHtml;
        }
      }
    );
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

      let src = videoEl ? videoEl.src : null;
      if (!src && videoEl) {
        const source = videoEl.querySelector("source");
        if (source) src = source.src;
      }
      if (!src && parent) {
        const v = parent.querySelector("video");
        if (v) src = v.src || (v.querySelector("source") ? v.querySelector("source").src : null);
      }

      handleVideoDownload(src, btn);
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
