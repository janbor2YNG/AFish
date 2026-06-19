// Tracking script for the phishing landing page (/track).
// Reads the campaign id (c), wave id (id) and recipient email from the URL,
// reports the click to the backend, then forwards to the awareness page.
function getParam(name) {
    return new URLSearchParams(window.location.search).get(name);
}

document.addEventListener("DOMContentLoaded", async function () {
    const campaignId = getParam('c');
    const id = getParam('id');
    const email = getParam('email');
    try {
        await fetch('/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ c: campaignId, id: id, email: email })
        });
    } catch (e) {
        // ignore network errors – still forward the user
    }
    window.location.href = "/awareness";
});
