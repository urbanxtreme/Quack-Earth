import { useState } from "react";
import Dashboard from "./Dashboard";

export default function App() {
  const [showDashboard, setShowDashboard] = useState<boolean>(true);
  const [placeQuery, setPlaceQuery] = useState<string>("Tokyo");

  const handleOpenMap = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setShowDashboard(true);
  };

  return (
    <main className="app-root">
      {!showDashboard ? (
        <section className="landing-screen">
          <div className="landing-card">
            <div className="brand-header">
              <div className="brand-icon-wrapper">
                <span className="brand-globe-icon">🌍</span>
              </div>
              <h1 className="brand-heading">Quack Earth</h1>
              <p className="brand-subheading">
                Edge-capable seismic risk anticipation & geospatial intelligence powered by PMTiles and MapLibre
              </p>
            </div>

            {/* Place name input form */}
            <form className="landing-search-form" onSubmit={handleOpenMap}>
              <div className="landing-input-group">
                <span className="landing-search-icon">📍</span>
                <input
                  type="text"
                  className="landing-input"
                  placeholder="Enter place name (e.g. Tokyo, San Francisco, Nepal)..."
                  value={placeQuery}
                  onChange={(e) => setPlaceQuery(e.target.value)}
                  id="landing-place-input"
                />
              </div>

              <div className="landing-quick-tags">
                <span className="quick-label">Suggestions:</span>
                {["Tokyo", "San Francisco", "Chile", "Nepal", "Turkey", "Kochi"].map((place) => (
                  <button
                    key={place}
                    type="button"
                    className="landing-tag-btn"
                    onClick={() => {
                      setPlaceQuery(place);
                    }}
                  >
                    {place}
                  </button>
                ))}
              </div>

              <div className="cta-container">
                <button
                  type="submit"
                  className="btn-primary"
                  id="open-map-button"
                >
                  <span>Launch Seismic Anticipation Engine</span>
                  <span className="btn-arrow">→</span>
                </button>
              </div>
            </form>

            <div className="features-preview">
              <div className="feature-pill">
                <span className="pill-dot" />
                <span>Cloud-Native Vector PMTiles</span>
              </div>
              <div className="feature-pill">
                <span className="pill-dot" />
                <span>Omori Short-Term Probabilities</span>
              </div>
              <div className="feature-pill">
                <span className="pill-dot" />
                <span>USGS & Edge Local Catalogs</span>
              </div>
            </div>
          </div>
        </section>
      ) : (
        <Dashboard
          onBackToLanding={() => setShowDashboard(false)}
          initialPlace={placeQuery.trim() || undefined}
        />
      )}
    </main>
  );
}