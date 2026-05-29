/**
 * tpgFlex Profile Manager
 * Shared module included by every page. Exposes window.tpgProfile.
 * All user feedback (speak, vibrate, notify) goes through this object so
 * the user's saved preferences are always respected.
 */
(function () {
  'use strict';

  window.tpgProfile = {
    _cache: null,

    // ── Identity ──────────────────────────────────────────────────────────────

    getUserId() {
      let id = localStorage.getItem('tpgflex_user_id');
      if (!id) {
        id = 'user_' + Math.random().toString(36).substring(2, 12);
        localStorage.setItem('tpgflex_user_id', id);
      }
      return id;
    },

    invalidateCache() {
      this._cache = null;
    },

    // ── Preferences ───────────────────────────────────────────────────────────

    async getPreferences() {
      if (this._cache) return this._cache;
      try {
        const r = await fetch(`/api/profile/${this.getUserId()}/ui-preferences`);
        if (!r.ok) throw new Error('not found');
        this._cache = await r.json();
      } catch (_) {
        // Fallback defaults — no backend needed
        this._cache = {
          ui_mode: 'default',
          audio_feedback: true,
          haptic_feedback: true,
          visual_feedback: true,
          high_contrast: false,
          large_text: false,
          voice_speed: 1.0,
          auto_announce_stops: false,
          preferred_language: 'fr',
          icon: '👤',
          label: 'Standard user',
          max_walking_distance: 500,
          step_length_metres: 0.75,
          scoring_profile: 'all',
          accessibility_profile: 'standard',
        };
      }
      return this._cache;
    },

    // ── UI mode application ───────────────────────────────────────────────────

    async applyUIMode() {
      const prefs = await this.getPreferences();
      document.body.classList.add(`ui-${prefs.ui_mode}`);
      if (prefs.high_contrast) document.body.classList.add('high-contrast');
      if (prefs.large_text)    document.body.classList.add('large-text');
      return prefs;
    },

    // ── Feedback primitives ───────────────────────────────────────────────────

    async speak(text) {
      const prefs = await this.getPreferences();
      if (!prefs.audio_feedback) return;
      if (!window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = prefs.preferred_language === 'fr' ? 'fr-FR'
                 : prefs.preferred_language === 'de' ? 'de-DE'
                 : prefs.preferred_language === 'it' ? 'it-IT'
                 : prefs.preferred_language === 'es' ? 'es-ES'
                 : 'en-US';
      utter.rate = prefs.voice_speed || 1.0;
      window.speechSynthesis.speak(utter);
    },

    async vibrate(pattern) {
      const prefs = await this.getPreferences();
      if (!prefs.haptic_feedback) return;
      if (navigator.vibrate) navigator.vibrate(pattern);
    },

    async notify(message, type = 'info') {
      const prefs = await this.getPreferences();
      if (!prefs.visual_feedback) return;
      const toast = document.createElement('div');
      toast.textContent = message;
      toast.className = `tpg-toast tpg-toast-${type}`;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    },

    // ── Combined feedback ─────────────────────────────────────────────────────

    async feedback(text, hapticPattern = [200], notifyType = 'info') {
      await Promise.all([
        this.speak(text),
        this.vibrate(hapticPattern),
        this.notify(text, notifyType),
      ]);
    },

    // ── Profile banner (shown when no profile saved) ───────────────────────────

    showSetupBannerIfNeeded() {
      // Only show once per session
      if (sessionStorage.getItem('tpg_banner_dismissed')) return;
      const existing = localStorage.getItem('tpgflex_user_id');
      // If user already has a persistent ID they've likely set up a profile.
      // We'll fetch and only show banner if accessibility_profile === 'standard'
      // (which is the auto-created default, not a deliberate choice).
      this.getPreferences().then(prefs => {
        if (prefs.accessibility_profile !== 'standard') return;
        const banner = document.createElement('div');
        banner.className = 'tpg-profile-banner';
        banner.innerHTML = `
          <span>👋 Personalize your experience —</span>
          <a href="/static/profile_setup.html">Set your accessibility profile</a>
          <button class="tpg-banner-close" aria-label="Dismiss">&times;</button>`;
        banner.querySelector('.tpg-banner-close').onclick = () => {
          banner.remove();
          sessionStorage.setItem('tpg_banner_dismissed', '1');
        };
        document.body.appendChild(banner);
      }).catch(() => {});
    },
  };
})();
