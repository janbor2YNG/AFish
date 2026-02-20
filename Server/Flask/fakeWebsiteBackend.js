function getIdFromURL() {
    // URL z.B.: http://localhost:5000/?id=123
    const params = new URLSearchParams(window.location.search);
    return params.get('id');
}
function getEmailFromURL() {
    // URL z.B.: http://localhost:5000/?email=hs@gmail.com
    const params = new URLSearchParams(window.location.search);
    return params.get('email');
}
document.addEventListener("DOMContentLoaded", async function() {
const id = getIdFromURL();
const email = getEmailFromURL();
await fetch('/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, id: id })
})
window.location.href = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";



});