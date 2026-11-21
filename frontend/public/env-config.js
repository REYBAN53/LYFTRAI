// Runtime configuration. The Docker image overwrites this file at container start from the
// API_BASE_URL environment variable; static hosts fall back to VITE_API_BASE_URL at build time.
window.__APP_CONFIG__ = window.__APP_CONFIG__ || {};
