import React, { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8020";

const weekdayMap = [
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
  { value: 7, label: "Sun" },
];

export default function App() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  async function fetchSettings() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/settings`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
    } catch (e) {
      console.error(e);
      setError("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
      showToast("Settings saved successfully ✅", "success");
    } catch (e) {
      console.error(e);
      setError("Failed to save settings");
      showToast("Failed to save settings ❌", "error");
    } finally {
      setSaving(false);
    }
  }


  function updateNumber(field, value) {
    const num = value === "" ? "" : Number(value);
    setSettings((prev) => ({ ...prev, [field]: num }));
  }

  function updateAvailability(index, field, value) {
    setSettings((prev) => {
      const next = [...prev.availability];
      next[index] = { ...next[index], [field]: value };
      return { ...prev, availability: next };
    });
  }

  function toggleDay(index, dayValue) {
    setSettings((prev) => {
      const next = [...prev.availability];
      const current = new Set(next[index].daysOfWeek);
      if (current.has(dayValue)) current.delete(dayValue);
      else current.add(dayValue);
      next[index] = {
        ...next[index],
        daysOfWeek: Array.from(current).sort((a, b) => a - b),
      };
      return { ...prev, availability: next };
    });
  }

  function addAvailability() {
    setSettings((prev) => ({
      ...prev,
      availability: [
        ...prev.availability,
        {
          daysOfWeek: [1, 2, 3, 4, 5],
          startTime: "13:00",
          endTime: "17:00",
        },
      ],
    }));
  }

  function removeAvailability(index) {
    setSettings((prev) => {
      const next = [...prev.availability];
      next.splice(index, 1);
      return { ...prev, availability: next };
    });
  }

  return (
    <div className="admin-app">
      <header className="admin-header">
        <div className="brand">
          <div className="logo">⚙️</div>
          <div>
            <div className="brand-title">Smart Delivery Admin</div>
            <div className="brand-sub">Scoring & Availability Settings</div>
          </div>
        </div>
        <div className="header-actions">
          <button className="btn ghost" onClick={fetchSettings} disabled={loading || saving}>
            Refresh
          </button>
          <button className="btn primary" onClick={saveSettings} disabled={!settings || saving}>
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </header>

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}

      <main className="admin-content">
        {loading && !settings && <div className="status">Loading settings...</div>}
        {error && <div className="status error">{error}</div>}

        {settings && (
          <>
            <section className="panel">
              <h2>Scoring & Delivery</h2>
              <div className="grid">
                <Field
                  label="Base delivery fee (cents)"
                  value={settings.baseDeliveryFeeCents}
                  onChange={(v) => updateNumber("baseDeliveryFeeCents", v)}
                />
                <Field
                  label="Minimum delivery fee (cents)"
                  value={settings.minDeliveryFeeCents}
                  onChange={(v) => updateNumber("minDeliveryFeeCents", v)}
                />
                <Field
                  label="Max discount (0–1)"
                  value={settings.maxDiscount}
                  onChange={(v) => updateNumber("maxDiscount", v)}
                />
                <Field
                  label="Discount curve K"
                  value={settings.k}
                  onChange={(v) => updateNumber("k", v)}
                />
                <Field
                  label="Radius (meters)"
                  value={settings.radiusM}
                  onChange={(v) => updateNumber("radiusM", v)}
                />
                <Field
                  label="Time window t0 (minutes)"
                  value={settings.t0Min}
                  onChange={(v) => updateNumber("t0Min", v)}
                />
                <Field
                  label="Min solo units"
                  value={settings.minSoloUnits}
                  onChange={(v) => updateNumber("minSoloUnits", v)}
                />
              </div>
              <p className="hint">
                These values directly affect the batching score and discounts. Changes apply immediately
                to new slot calculations.
              </p>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>Availability Windows</h2>
                <button className="btn small ghost" onClick={addAvailability}>
                  + Add Window
                </button>
              </div>
              {settings.availability.length === 0 && (
                <div className="status muted">No availability windows configured.</div>
              )}

              <div className="availability-list">
                {settings.availability.map((w, idx) => (
                  <div key={idx} className="availability-card">
                    <div className="availability-top">
                      <div className="chip">Window #{idx + 1}</div>
                      <button
                        className="btn tiny ghost"
                        onClick={() => removeAvailability(idx)}
                        disabled={settings.availability.length === 1}
                      >
                        Remove
                      </button>
                    </div>
                    <div className="availability-body">
                      <div className="days-row">
                        <span className="label">Days</span>
                        <div className="days">
                          {weekdayMap.map((d) => (
                            <button
                              key={d.value}
                              type="button"
                              className={
                                "day-pill" +
                                (w.daysOfWeek.includes(d.value) ? " active" : "")
                              }
                              onClick={() => toggleDay(idx, d.value)}
                            >
                              {d.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="time-row">
                        <div>
                          <label className="label">Start time</label>
                          <input
                            type="time"
                            value={w.startTime}
                            onChange={(e) =>
                              updateAvailability(idx, "startTime", e.target.value)
                            }
                          />
                        </div>
                        <div>
                          <label className="label">End time</label>
                          <input
                            type="time"
                            value={w.endTime}
                            onChange={(e) =>
                              updateAvailability(idx, "endTime", e.target.value)
                            }
                          />
                        </div>
                      </div>
                    </div>
                    <p className="hint small">
                      Only slots whose <b>startAt</b> falls within these days + times will be offered
                      to customers.
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <h2>API Info</h2>
              <div className="info-grid">
                <div>
                  <div className="label">API base</div>
                  <div className="mono">{API_BASE}</div>
                </div>
                <div>
                  <div className="label">Settings endpoint</div>
                  <div className="mono">{API_BASE}/settings</div>
                </div>
              </div>
            </section>
          </>
        )}
      </main>

      <footer className="admin-footer">
        <span>Smart Delivery Admin • v1</span>
      </footer>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <div className="field">
      <label className="label">{label}</label>
      <input
        type="number"
        value={value === "" ? "" : value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
