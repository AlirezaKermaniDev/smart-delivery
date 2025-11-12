import React, { useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Fix default marker icons for Vite
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// ---- Config ----
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8020";

// Seed products (same as backend bootstrap)
const PRODUCTS = [
  { id: "p_1", name: "Classic Cookie", priceCents: 300, unitFactor: 1, color: "#FFB703" },
  { id: "p_2", name: "Double Choc", priceCents: 350, unitFactor: 1, color: "#FB8500" },
  { id: "p_3", name: "Party Box (6)", priceCents: 1600, unitFactor: 6, color: "#8ECAE6" },
];

const money = (c) => `€${(c / 100).toFixed(2)}`;
const pct = (p) => `${(p * 100).toFixed(1)}%`;

function useNowIsoRange(days = 3) {
  return useMemo(() => {
    const now = new Date();
    const to = new Date(now.getTime() + days * 86400000);
    return { fromISO: now.toISOString(), toISO: to.toISOString() };
  }, [days]);
}

function ClickMarker({ position, onChange }) {
  useMapEvents({
    click(e) {
      onChange([e.latlng.lat, e.latlng.lng]);
    },
  });
  return position ? <Marker position={position} /> : null;
}

// ---------- Main App ----------
export default function App() {
  const [step, setStep] = useState(1);

  // Step 1: cart
  const [cartId, setCartId] = useState(null);
  const [items, setItems] = useState({ p_1: 2, p_2: 1, p_3: 0 });

  // Step 2: location
  const [pos, setPos] = useState([60.1699, 24.9384]); // Helsinki default

  // Step 3: slots + quote
  const [slots, setSlots] = useState([]);
  const [selectedSlotId, setSelectedSlotId] = useState(null);
  const [quote, setQuote] = useState(null);

  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const { fromISO, toISO } = useNowIsoRange(3);

  function notify(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  function resetAll() {
    setStep(1);
    setCartId(null);
    setItems({ p_1: 2, p_2: 1, p_3: 0 });
    setPos([60.1699, 24.9384]);
    setSlots([]);
    setSelectedSlotId(null);
    setQuote(null);
  }

  // ---------- Actions ----------
  async function clearDb(full = true) {
    setLoading(true);
    try {
      const url = `${API_BASE}/dev/clear-db${full ? "?full=true" : ""}`;
      const res = await fetch(url, { method: "POST" });
      await res.json();
      notify(full ? "Database cleared & slots reseeded." : "Database cleared (soft).", "success");
    } catch (e) {
      notify("Failed to clear DB", e);
    } finally {
      setLoading(false);
    }
  }

  // Step 1: create cart
  async function createCart() {
    setLoading(true);
    try {
      const body = {
        items: Object.entries(items)
          .filter(([, q]) => q > 0)
          .map(([productId, qty]) => ({ productId, qty })),
      };
      if (body.items.length === 0) {
        notify("Add at least one product.", "error");
        setLoading(false);
        return;
      }
      const res = await fetch(`${API_BASE}/cart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCartId(data.cartId);
      notify("Cart created.", "success");
      setStep(2);
    } catch (e) {
      notify("Failed to create cart", e);
    } finally {
      setLoading(false);
    }
  }

  // Step 3: fetch slots
  async function fetchSlots() {
    if (!cartId) {
      notify("Create a cart first.", "error");
      return;
    }
    setLoading(true);
    try {
      const url = `${API_BASE}/delivery/slots?cartId=${cartId}&lat=${pos[0]}&lon=${pos[1]}&fromISO=${encodeURIComponent(
        fromISO
      )}&toISO=${encodeURIComponent(toISO)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSlots(data.slots || []);
      setSelectedSlotId(null);
      notify(`Loaded ${data.slots?.length || 0} slots.`, "success");
    } catch (e) {
      notify("Failed to fetch slots", e);
    } finally {
      setLoading(false);
    }
  }

  async function quoteAndPay(slotId) {
    if (!cartId) {
      notify("Create a cart first.", "error");
      return;
    }
    setLoading(true);
    try {
      // Quote
      const resQ = await fetch(`${API_BASE}/checkout/quote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cartId, slotId, lat: pos[0], lon: pos[1] }),
      });
      const txt = await resQ.text();
      if (!resQ.ok) throw new Error(txt);
      const q = JSON.parse(txt);
      setSelectedSlotId(slotId);
      setQuote(q);

      // Payment intent (stub)
      const resP = await fetch(`${API_BASE}/payments/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quoteId: q.quoteId }),
      });
      if (!resP.ok) throw new Error(await resP.text());

      // Webhook success
      const resW = await fetch(`${API_BASE}/webhooks/payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event: "payment_succeeded", quoteId: q.quoteId }),
      });
      if (!resW.ok) throw new Error(await resW.text());

      notify("Order confirmed! 🎉", "success");
      setStep(4);
    } catch (e) {
      try {
        const detail = JSON.parse(e.message);
        if (detail?.detail?.error === "SOLO_MIN_UNITS_REQUIRED") {
          notify(detail.detail.message, "warn");
        } else {
          notify("Quote/payment failed.", "error");
        }
      } catch {
        notify("Quote/payment failed.", "error");
      }
    } finally {
      setLoading(false);
    }
  }

  // ---------- UI blocks ----------
  const Header = () => (
    <header className="header">
      <div className="brand">
        <div className="logo">🍪</div>
        <div>
          <div className="brand-title">Smart Delivery</div>
          <div className="brand-sub">Batch & Save</div>
        </div>
      </div>
      <div className="steps">
        <StepBadge n={1} active={step === 1} done={step > 1} label="Products" />
        <Connector />
        <StepBadge n={2} active={step === 2} done={step > 2} label="Location" />
        <Connector />
        <StepBadge n={3} active={step === 3} done={step > 3} label="Time Slots" />
        <Connector />
        <StepBadge n={4} active={step === 4} done={step > 4} label="Success" />
      </div>
      <div className="header-actions">
        <button className="btn ghost" onClick={() => clearDb(true)} disabled={loading}>Reset DB</button>
        <button className="btn ghost" onClick={resetAll}>Restart</button>
      </div>
    </header>
  );

  const Footer = () => (
    <footer className="footer">
      <div>© {new Date().getFullYear()} Smart Delivery • Demo</div>
    </footer>
  );

  return (
    <div className="app">
      <Header />

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}

      <main className="content">
        {step === 1 && (
          <section className="page">
            <h1 className="page-title">Choose your treats</h1>
            <div className="grid two">
              <ProductGallery items={items} setItems={setItems} />
              <CartPanel items={items} />
            </div>
            <div className="actions">
              <button className="btn primary" onClick={createCart} disabled={loading}>
                Create Cart & Continue →
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="page">
            <h1 className="page-title">Select your location</h1>
            <p className="muted">Click on the map to place your pin. We’ll use this to find nearby deliveries.</p>
            <div className="map-wrap">
              <MapContainer center={pos} zoom={14} style={{ height: "100%", width: "100%" }}>
                <TileLayer
                  attribution='&copy; OpenStreetMap contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <ClickMarker position={pos} onChange={setPos} />
              </MapContainer>
            </div>
            <div className="row">
              <div className="chip">Lat: {pos[0].toFixed(6)}</div>
              <div className="chip">Lon: {pos[1].toFixed(6)}</div>
            </div>
            <div className="actions">
              <button className="btn" onClick={() => setStep(1)}>← Back</button>
              <button className="btn primary" onClick={() => { setStep(3); fetchSlots(); }} disabled={loading}>
                Continue to Time Slots →
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="page">
            <h1 className="page-title">Choose a time slot (next 3 days)</h1>
            <p className="muted">We’ll highlight the best deals based on batching near your location.</p>

            <div className="slots-grid">
              {slots.length === 0 && <div className="empty">No slots yet. Try “Refresh Slots”.</div>}
              {slots.map((s) => (
                <div key={s.slotId} className={`slot-card ${s.label.includes("Best") ? "best" : s.label.includes("Good") ? "good" : ""} ${selectedSlotId === s.slotId ? "selected" : ""}`}>
                  <div className="slot-top">
                    <div className="slot-title">{new Date(s.startAt).toLocaleString()}</div>
                    <div className="badge">{s.label}</div>
                  </div>
                  <div className="slot-row">
                    <span>Discount</span>
                    <strong>{pct(s.discountPct)}</strong>
                  </div>
                  <div className="slot-row">
  <span>Delivery Fee</span>
  <strong>
    {money(s.finalDeliveryFeeCents)}
    {s.finalDeliveryFeeCents < s.baseDeliveryFeeCents && (
      <span className="strikethrough">{money(s.baseDeliveryFeeCents)}</span>
    )}
  </strong>
</div>
                  <div className="slot-cap">Capacity {s.capacity.used}/{s.capacity.total}</div>
                  {s.requiresSoloMinUnits && (
                    <div className="warn">No nearby deliveries. Minimum {s.soloMinUnits} units for this slot.</div>
                  )}
                  <div className="slot-actions">
                    <button className="btn primary" onClick={() => quoteAndPay(s.slotId)} disabled={loading}>
                      Finalize Order
                    </button>
                    <button className="btn ghost" onClick={() => setSelectedSlotId(s.slotId)}>
                      Select
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="actions">
              <button className="btn" onClick={() => setStep(2)}>← Back</button>
              <button className="btn" onClick={fetchSlots} disabled={loading}>⟳ Refresh Slots</button>
            </div>
          </section>
        )}

        {step === 4 && (
          <section className="page">
            <div className="success-card">
              <div className="success-emoji">🎉</div>
              <h1>Order Confirmed!</h1>
              {quote && (
                <>
                  <div className="summary-row"><span>Quote ID</span><strong>{quote.quoteId}</strong></div>
                  <div className="summary-row"><span>Subtotal</span><strong>{money(quote.amounts.subtotalCents)}</strong></div>
                  <div className="summary-row"><span>Delivery</span><strong>{money(quote.amounts.deliveryFeeCents)}</strong></div>
                  <div className="summary-row"><span>Discount</span><strong>-{money(quote.amounts.discountCents)}</strong></div>
                  <div className="summary-row total"><span>Total</span><strong>{money(quote.amounts.totalCents)}</strong></div>
                </>
              )}
              <div className="actions">
                <button className="btn" onClick={() => setStep(3)}>← Back</button>
                <button className="btn primary" onClick={resetAll}>Restart Flow</button>
              </div>
              <p className="muted">Tip: Now repeat the flow with a nearby location to see discounts improve for the same slot.</p>
            </div>
          </section>
        )}
      </main>

      <Footer />
    </div>
  );
}

// ---------- Components ----------
function ProductGallery({ items, setItems }) {
  return (
    <div className="card">
      <div className="card-title">Products</div>
      <div className="product-grid">
        {PRODUCTS.map((p) => (
          <div className="product-card" key={p.id} style={{ borderTopColor: p.color }}>
            <div className="product-thumb" style={{ background: p.color }}>
              {/* Placeholder image color block */}
              <div className="thumb-text">{p.name.split(" ")[0]}</div>
            </div>
            <div className="product-info">
              <div className="product-name">{p.name}</div>
              <div className="product-meta">
                <span>{money(p.priceCents)}</span>
                <span className="muted">unit {p.unitFactor}</span>
              </div>
            </div>
            <div className="qty-row">
              <button className="btn small" onClick={() => setItems((s) => ({ ...s, [p.id]: Math.max(0, (s[p.id] || 0) - 1) }))}>−</button>
              <input
                type="number"
                value={items[p.id] || 0}
                min={0}
                onChange={(e) => setItems((s) => ({ ...s, [p.id]: Math.max(0, parseInt(e.target.value || "0", 10)) }))}
              />
              <button className="btn small" onClick={() => setItems((s) => ({ ...s, [p.id]: (s[p.id] || 0) + 1 }))}>+</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CartPanel({ items }) {
  const lines = PRODUCTS
    .filter((p) => (items[p.id] || 0) > 0)
    .map((p) => ({
      name: p.name,
      qty: items[p.id],
      priceCents: p.priceCents,
      line: p.priceCents * (items[p.id] || 0),
    }));

  const total = lines.reduce((a, b) => a + b.line, 0);

  return (
    <div className="card">
      <div className="card-title">Cart</div>
      {lines.length === 0 ? (
        <div className="empty">Your cart is empty. Add something tasty!</div>
      ) : (
        <div className="cart-list">
          {lines.map((l, idx) => (
            <div className="cart-row" key={idx}>
              <div>{l.name} × {l.qty}</div>
              <div className="price">{money(l.line)}</div>
            </div>
          ))}
          <div className="cart-divider" />
          <div className="cart-row total">
            <div>Subtotal</div>
            <div className="price">{money(total)}</div>
          </div>
        </div>
      )}
      <div className="hint">Discounts apply at the time slot step based on batching near your location.</div>
    </div>
  );
}

function StepBadge({ n, label, active, done }) {
  return (
    <div className={`step-badge ${active ? "active" : ""} ${done ? "done" : ""}`}>
      <div className="step-num">{n}</div>
      <div className="step-label">{label}</div>
    </div>
  );
}

function Connector() {
  return <div className="connector" />;
}
