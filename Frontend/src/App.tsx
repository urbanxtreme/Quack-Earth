import { useState } from "react";
import MapViewer from "./MapViewer";

export default function App() {
  const [showMap, setShowMap] = useState<boolean>(false);
  const [placeQuery, setPlaceQuery] = useState<string>("");

  const handleOpenMap = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setShowMap(true);
  };

  return (
    <main className="app-root">
      {!showMap ? (
        <section className="landing-screen">
          <div className="landing-card">
            <div className="brand-header">
              <div className="brand-icon-wrapper">
                <span className="brand-globe-icon">🌍</span>
              </div>
              <h1 className="brand-heading">Quack Earth</h1>
              <p className="brand-subheading">
                Interactive seismic & geospatial heatmap explorer powered by PMTiles and MapLibre
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
                {["Tokyo", "San Francisco", "Chile", "Nepal", "Turkey"].map((place) => (
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
                  <span>Click to open map</span>
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
                <span>Dynamic Radial Heatmaps</span>
              </div>
              <div className="feature-pill">
                <span className="pill-dot" />
                <span>USGS Real-Time Earthquake Integration</span>
              </div>
            </div>
          </div>
        </section>
      ) : (
        <MapViewer
          onBack={() => setShowMap(false)}
          initialPlace={placeQuery.trim() || undefined}
        />
      )}
    </main>
  );
}