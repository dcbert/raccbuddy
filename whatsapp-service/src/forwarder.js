/**
 * Forwards a WhatsApp message payload to the Python core REST API.
 *
 * Retries up to 3 times with exponential back-off on transient failures.
 */

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;

/**
 * POST the message payload to the Python core.
 *
 * @param {string} coreUrl  - Base URL of the Python core (e.g. http://localhost:8000)
 * @param {object} payload  - Message payload object
 */
async function forwardMessage(coreUrl, payload) {
  const url = `${coreUrl}/api/messages`;
  console.log(`🚀 Forwarding message from ${payload.contact_name} to core...`);
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        console.log(
          `📨 Forwarded message from ${payload.contact_name} (${payload.from_id})`
        );
        return;
      }

      // Non-retryable client errors
      if (res.status >= 400 && res.status < 500) {
        const body = await res.text();
        console.error(
          `❌ Core rejected message (${res.status}): ${body}`
        );
        return;
      }

      // Server error — retry
      console.warn(
        `⚠️  Core returned ${res.status}, retrying (${attempt}/${MAX_RETRIES})...`
      );
    } catch (err) {
      console.warn(
        `⚠️  Failed to reach core (attempt ${attempt}/${MAX_RETRIES}): ${err.message}`
      );
    }

    // Exponential back-off
    if (attempt < MAX_RETRIES) {
      await sleep(BASE_DELAY_MS * Math.pow(2, attempt - 1));
    }
  }

  console.error(
    `❌ Gave up forwarding message from ${payload.contact_name} after ${MAX_RETRIES} attempts`
  );
}

/** Helper: sleep for a given duration (ms). */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = { forwardMessage };
