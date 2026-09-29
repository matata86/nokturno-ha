// Nokturno 9.0.2 – jen v původním repozitáři: karta ukazuje, kam se integrace přestěhovala.
const NOVE_REPO = "https://github.com/nokturno-app/nokturno-ha";
const TEXT = {
  cs: ["Nokturno se přestěhovalo", "Integrace se teď vydává z nového repozitáře a tahle verze už nic nedělá. V HACS odeber starý repozitář Nokturna, přidej nový (kategorie Integrace), stáhni Nokturno a restartuj Home Assistant. Nastavení zůstane.", "Otevřít nový repozitář"],
  sk: ["Nokturno sa presťahovalo", "Integrácia sa teraz vydáva z nového repozitára a táto verzia už nič nerobí. V HACS odober starý repozitár Nokturna, pridaj nový (kategória Integrácia), stiahni Nokturno a reštartuj Home Assistant. Nastavenia zostanú.", "Otvoriť nový repozitár"],
  en: ["Nokturno has moved", "The integration is now released from a new repository and this version does nothing. In HACS remove the old Nokturno repository, add the new one (category Integration), download Nokturno and restart Home Assistant. Your settings stay.", "Open the new repository"],
};

class NokturnoMovedCard extends HTMLElement {
  setConfig() {}
  getCardSize() { return 3; }
  set hass(hass) {
    if (this._done) return;
    this._done = true;
    const lang = (hass.locale?.language || hass.language || "cs").slice(0, 2);
    const [title, body, link] = TEXT[lang] || TEXT.en;
    this.innerHTML = `<ha-card header="${title}"><div class="card-content">
      <ha-alert alert-type="warning">${body}</ha-alert>
      <p><a href="${NOVE_REPO}" target="_blank" rel="noopener">${link}</a> – ${NOVE_REPO}</p>
      </div></ha-card>`;
  }
}

for (const tag of ["nokturno-card"]) {
  try { if (!customElements.get(tag)) customElements.define(tag, NokturnoMovedCard); } catch (e) { /* už definováno */ }
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "nokturno-card")) window.customCards.push({
  type: "nokturno-card", name: "Nokturno", description: "Nokturno se přestěhovalo – " + NOVE_REPO,
});
