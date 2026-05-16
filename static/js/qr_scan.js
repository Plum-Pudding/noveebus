/**
 * qr_scan.js
 * QR scanning utilities using html5-qrcode library.
 */

class QRScanner {
  constructor(elementId, onScan, onError) {
    this.elementId = elementId;
    this.onScan = onScan;
    this.onError = onError || console.error;
    this.scanner = null;
  }

  start() {
    if (this.scanner) {
      this.stop();
    }
    this.scanner = new Html5Qrcode(this.elementId);
    return this.scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 250, height: 250 } },
      (decodedText, decodedResult) => {
        this.onScan(decodedText, decodedResult);
      },
      (errorMessage) => {
        // Ignore scan frame errors silently
      }
    ).catch(this.onError);
  }

  stop() {
    if (this.scanner) {
      return this.scanner.stop().then(() => {
        this.scanner = null;
      }).catch(console.error);
    }
    return Promise.resolve();
  }

  isRunning() {
    return this.scanner !== null;
  }
}

/**
 * Quick-start a single-scan QR session.
 * Stops after first successful scan.
 */
function startSingleScan(elementId, onResult) {
  const scanner = new QRScanner(elementId, async (text) => {
    await scanner.stop();
    onResult(text);
  });
  scanner.start();
  return scanner;
}
