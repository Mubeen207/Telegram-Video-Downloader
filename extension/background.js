// TG Private Video Downloader - Background Service Worker

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "download_video") {
    const { videoUrl, filename } = request;
    
    chrome.downloads.download({
      url: videoUrl,
      filename: filename || `Telegram_Video_${Date.now()}.mp4`,
      saveAs: true
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        sendResponse({ success: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ success: true, downloadId: downloadId });
      }
    });

    return true; // Keep message channel open for async response
  }
});
