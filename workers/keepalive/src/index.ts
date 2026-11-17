/* Keep-alive für das Render-Free-Backend.
 *
 * Render Free schaltet Instanzen nach 15 Minuten ohne Traffic ab. Der erste
 * Request während des Kaltstarts kann 502/404 liefern (beobachtet: OPTIONS-
 * Preflight → „Load failed" im Browser). Dieser Cron-Worker pingt alle
 * 5 Minuten /api/health und hält die Instanz dadurch dauerhaft wach
 * (~744 h/Monat < 750 h Free-Kontingent).
 *
 * Deploy:  cd workers/keepalive && npx wrangler deploy
 * Logs:    npx wrangler tail zenji-keepalive
 */

const TARGET = "https://zenji-api.onrender.com/api/health";

export default {
  async scheduled(): Promise<void> {
    try {
      const response = await fetch(TARGET);
      const body = await response.text();
      console.log(`keepalive: HTTP ${response.status} ${body.slice(0, 80)}`);
    } catch (error) {
      console.error("keepalive fehlgeschlagen:", String(error));
    }
  },
};
