// TG Private Video Downloader - Content Script for web.telegram.org

console.log("[TG Downloader] Content script loaded on Telegram Web.");

function injectDownloadButtons() {
  // Select video elements and wrappers on Telegram Web
  const videoContainers = document.querySelectorAll(
    ".media-widget-video, .video-player, .message-media-video, .media-container, .Bubble .video-wrapper, video"
  );

  videoContainers.forEach((container) => {
    const parent = container.parentElement || container;
    if (parent.querySelector(".tg-ext-download-btn")) return; // Already injected

    const videoEl = container.tagName === "VIDEO" ? container : container.querySelector("video");
    
    if (videoEl || container.dataset.src) {
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

        if (!src) {
          alert("[TG Downloader] Play the video once to load the media buffer, then click Download HD.");
          return;
        }

        const filename = `Telegram_Video_${Date.now()}.mp4`;

        chrome.runtime.sendMessage(
          { action: "download_video", videoUrl: src, filename: filename },
          (response) => {
            if (response && response.success) {
              btn.innerText = "Downloading...";
              setTimeout(() => { btn.innerHTML = "<span>Download HD</span>"; }, 3000);
            } else {
              window.open(src, "_blank");
            }
          }
        );
      };

      if (getComputedStyle(parent).position === "static") {
        parent.style.position = "relative";
      }

      parent.appendChild(btn);
    }
  });
}

// Observe DOM changes on Telegram Web
const observer = new MutationObserver(() => {
  injectDownloadButtons();
});

observer.observe(document.body, { childList: true, subtree: true });
setInterval(injectDownloadButtons, 2000);
